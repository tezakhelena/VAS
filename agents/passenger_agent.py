from spade.agent import Agent
from spade.behaviour import FSMBehaviour, State
from spade.message import Message
from tabulate import tabulate
import random
import math
import time


class PassengerAgent(Agent):

    class PassengerFSM(FSMBehaviour):
        async def on_start(self):
            self.agent.retry_count = 0
            self.agent.chosen_taxi = None
            self.agent.chosen_eta = None
            self.agent.knowledge_base = {"late_taxis": set()}

            print(f"\nPassenger {self.agent.jid} FSM STARTED")

        async def on_end(self):
            print(f"\n========== Izvješće putnika: {self.agent.jid} ==========")
            print(f"Inicijalna lokacija (preuzimanje): {self.agent.location}")
            print(f"Odredište vožnje: {self.agent.destination}")
            print(f"Broj pokušaja ponovnog slanja zahtjeva: {self.agent.retry_count}")
            print(f"Odabrani taksi: {self.agent.chosen_taxi}")
            print(f"Odabrano procijenjeno vrijeme dolaska (ETA): {self.agent.chosen_eta} min")
            print(f"Zapamćeni zakašnjeli taksiji: {self.agent.knowledge_base['late_taxis']}")
            print("====================================================\n")

            await self.agent.stop()

    class InitState(State):
        async def run(self):
            self.agent.taxi_jids = [
                "taxi1@localhost",
                "taxi2@localhost",
                "taxi3@localhost",
            ]

            self.agent.location = (
                random.randint(0, 100),
                random.randint(0, 100)
            )

            self.agent.destination = (
                random.randint(0, 100),
                random.randint(0, 100)
            )

            self.agent.responses = []

            print(f"Lokacija putnika [{self.agent.jid}]: {self.agent.location} | Odredište putnika [{self.agent.jid}]: {self.agent.destination}")

            self.set_next_state("SEND_CFP")

    class SendCfpState(State):
        async def run(self):
            self.agent.responses.clear()

            print(f"[{self.agent.jid}] šalje zahtjev za ponudu (CFP) svim taksijima")

            for jid in self.agent.taxi_jids:
                msg = Message(to=jid)
                msg.set_metadata("performative", "cfp")
                msg.body = (
                    f"Potrebno preuzimanje na lokaciji {self.agent.location[0]},{self.agent.location[1]}"
                )
                await self.send(msg)
                print(f"CFP poslan {jid}")

            self.set_next_state("WAIT_RESPONSES")

    class WaitResponsesState(State):
        async def run(self):
            print(f"[{self.agent.jid}] čeka ponude taksija...")

            for _ in self.agent.taxi_jids:
                msg = await self.receive(timeout=10)
                if msg and msg.metadata.get("performative") == "propose":
                    eta_str, loc_str = msg.body.split("|")
                    eta = int(eta_str)
                    taxi_loc = tuple(map(int, loc_str.split(",")))
                    dist = round(math.dist(self.agent.location, taxi_loc), 2)

                    self.agent.responses.append(
                        (str(msg.sender), eta, taxi_loc, dist)
                    )

            if not self.agent.responses:
                print("Nema ponuda")
                self.set_next_state("RETRY_CFP")
            else:
                self.set_next_state("SELECT_TAXI")

    class RetryCfpState(State):
        async def run(self):
            self.agent.retry_count += 1

            if self.agent.retry_count > 3:
                print(f"[{self.agent.jid}]: Nema dostupnih taksija nakon ponovnih pokušaja")
                self.set_next_state("END")
                return

            print(
                f"[{self.agent.jid}]: Ponavlja slanje zahtjeva (pokušaj #{self.agent.retry_count})"
            )

            self.set_next_state("SEND_CFP")

    class SelectTaxiState(State):
        async def run(self):
            print("\nPrimljene ponude:")
            print(f"Ukupan broj taksija koji su poslali ponudu: {len(self.agent.responses)}")

            print(tabulate(
                self.agent.responses,
                headers=["Taksi", "ETA (min)", "Lokacija taksija", "Udaljenost (km)"]
            ))

            best = min(self.agent.responses, key=lambda x: x[1])
            self.agent.chosen_taxi = best[0]
            self.agent.chosen_eta = best[1]

            print(
                f"[{self.agent.jid}] ODABRAO taksi {best[0]} s procijenjenim vremenom dolaska {best[1]} min"
            )

            for jid, eta, _, _ in self.agent.responses:
                reply = Message(to=jid)
                if jid == best[0]:
                    reply.set_metadata("performative", "accept-proposal")
                    reply.body = (
                        f"ACCEPT|"
                        f"{self.agent.location[0]},{self.agent.location[1]}|"
                        f"{self.agent.destination[0]},{self.agent.destination[1]}|"
                        f"{self.agent.jid}"
                    )
                    print(f"Accepted: {jid}")
                else:
                    reply.set_metadata("performative", "reject-proposal")
                    reply.body = "REJECT"
                    print(f"Odbijen: {jid} — Odabran je {best[0]} s {best[1]} min")

                await self.send(reply)

            self.set_next_state("WAIT_FOR_TAXI")

    class WaitForTaxiState(State):
        async def run(self):
            print(f"[{self.agent.jid}]: čeka dolazak taksija {self.agent.chosen_taxi} na lokaciju preuzimanja {self.agent.location}")

            while True:
                msg = await self.receive(timeout=5)
                if msg and msg.metadata.get("performative") == "inform":
                    print(
                        f"[{self.agent.jid}]: Vožnja s taksijem {self.agent.chosen_taxi} je završena, putnik je stigao na odredište"
                    )
                    self.set_next_state("END")
                    return

    class EndState(State):
        async def run(self):
            print(f"Passenger {self.agent.jid} FSM END")
            self.kill()

    async def setup(self):
        print(f"Passenger Agent {self.name} started")

        fsm = self.PassengerFSM()
        fsm.add_state("INIT", self.InitState(), initial=True)
        fsm.add_state("SEND_CFP", self.SendCfpState())
        fsm.add_state("WAIT_RESPONSES", self.WaitResponsesState())
        fsm.add_state("RETRY_CFP", self.RetryCfpState())
        fsm.add_state("SELECT_TAXI", self.SelectTaxiState())
        fsm.add_state("WAIT_FOR_TAXI", self.WaitForTaxiState())
        fsm.add_state("END", self.EndState())

        fsm.add_transition("INIT", "SEND_CFP")
        fsm.add_transition("SEND_CFP", "WAIT_RESPONSES")
        fsm.add_transition("WAIT_RESPONSES", "SELECT_TAXI")
        fsm.add_transition("WAIT_RESPONSES", "RETRY_CFP")
        fsm.add_transition("RETRY_CFP", "SEND_CFP")
        fsm.add_transition("RETRY_CFP", "END")
        fsm.add_transition("SELECT_TAXI", "WAIT_FOR_TAXI")
        fsm.add_transition("WAIT_FOR_TAXI", "END")

        self.add_behaviour(fsm)