from spade.agent import Agent
from spade.behaviour import FSMBehaviour, State
from spade.message import Message
import math
import asyncio
from colorama import init, Fore, Style

init(autoreset=True)


class TaxiAgent(Agent):
    def __init__(self, jid, password, location):
        super().__init__(jid, password)
        self.location = location
        self.available = True
        self.current_request = None
        self.pickup_location = None
        self.destination_location = None
        self.passenger_jid = None
        self.just_finished_ride = True

    class TaxiFSM(FSMBehaviour):
        async def on_start(self):
            print(
                Fore.BLUE + f"\n[{self.agent.name}] FSM STARTED | Inicijalna lokacija taksija: {self.agent.location}"
            )

    class WaitState(State):
        async def run(self):
            if self.agent.just_finished_ride:
                print(Fore.GREEN + f"[{self.agent.name}]: Status: AVAILABLE | Čekam zahtjev za prijevoz...")
                self.agent.just_finished_ride = False

            msg = await self.receive(timeout=30)

            if msg and msg.metadata.get("performative") == "cfp" and self.agent.available:
                self.agent.current_request = msg
                print(Fore.LIGHTYELLOW_EX + f"[{self.agent.name}]: Primljen zahtjev od putnika {msg.sender} | {msg.body}")
                self.set_next_state("PROPOSE")
            else:
                self.set_next_state("WAIT")

    class ProposeState(State):
        async def run(self):
            msg = self.agent.current_request

            x, y = map(int, msg.body.split()[-1].split(","))
            pickup = (x, y)

            dist = math.dist(self.agent.location, pickup)
            eta = round((dist / 55) * 60)

            reply = Message(to=str(msg.sender))
            reply.set_metadata("performative", "propose")
            reply.body = f"{eta}|{self.agent.location[0]},{self.agent.location[1]}"
            await self.send(reply)

            print(Fore.YELLOW + f"[{self.agent.name}]: POSLANA PONUDA putniku {msg.sender} | ETA: {eta} min")
            self.set_next_state("WAIT_RESPONSE")

    class WaitResponseState(State):
        async def run(self):
            expected = str(self.agent.current_request.sender)
            print(Fore.CYAN + f"[{self.agent.name}]: Čekam ODGOVOR od putnika {expected}")

            for _ in range(30):
                msg = await self.receive(timeout=1)
                if not msg or str(msg.sender) != expected:
                    continue

                if msg.metadata.get("performative") == "accept-proposal":
                    _, pickup, dest, passenger = msg.body.split("|")

                    self.agent.pickup_location = tuple(map(int, pickup.split(",")))
                    self.agent.destination_location = tuple(map(int, dest.split(",")))
                    self.agent.passenger_jid = passenger
                    self.agent.available = False

                    print(Fore.GREEN + f"[{self.agent.name}]: Putnik {passenger} prihvatio vožnju | Preuzimanje: {self.agent.pickup_location} | Odredište: {self.agent.destination_location}")
                    self.set_next_state("MOVE_TO_PICKUP")
                    return

                elif msg.metadata.get("performative") == "reject-proposal":
                    print(Fore.RED + f"[{self.agent.name}]: Odbijen od strane putnika")
                    break

            self.agent.current_request = None
            self.set_next_state("WAIT")

    class MoveToPickupState(State):
        async def run(self):
            cur = list(self.agent.location)
            tgt = self.agent.pickup_location

            print(Fore.LIGHTBLUE_EX + f"[{self.agent.name}]: KREĆEM prema mjestu preuzimanja {tgt}")

            while tuple(cur) != tgt:
                cur[0] += (tgt[0] > cur[0]) - (tgt[0] < cur[0])
                cur[1] += (tgt[1] > cur[1]) - (tgt[1] < cur[1])
                print(Fore.LIGHTBLACK_EX + f"[{self.agent.name}]: Trenutna lokacija taksija: {tuple(cur)}")
                await asyncio.sleep(0.2)

            self.agent.location = tuple(cur)
            print(Fore.LIGHTGREEN_EX + f"[{self.agent.name}]: Stigao na lokaciju preuzimanja | Putnik {self.agent.passenger_jid} ulazi u vozilo")
            self.set_next_state("MOVE_TO_DESTINATION")

    class MoveToDestinationState(State):
        async def run(self):
            cur = list(self.agent.location)
            tgt = self.agent.destination_location

            print(Fore.GREEN + f"[{self.agent.name}]: VOŽNJA ZAPOČELA | Vožnja s putnikom {self.agent.passenger_jid} prema odredištu {tgt}")

            while tuple(cur) != tgt:
                cur[0] += (tgt[0] > cur[0]) - (tgt[0] < cur[0])
                cur[1] += (tgt[1] > cur[1]) - (tgt[1] < cur[1])
                print(Fore.LIGHTBLACK_EX + f"[{self.agent.name}]: Prevozi putnika {self.agent.passenger_jid} – Trenutna lokacija: {tuple(cur)}")
                await asyncio.sleep(0.2)

            self.agent.location = tuple(cur)
            self.set_next_state("ARRIVED")

    class ArrivedState(State):
        async def run(self):
            msg = Message(to=self.agent.passenger_jid)
            msg.set_metadata("performative", "inform")
            msg.body = "ARRIVED"
            await self.send(msg)

            print(Fore.MAGENTA + f"[{self.agent.name}]: Završena vožnja | Putnik {self.agent.passenger_jid} je stigao")

            self.agent.available = True
            self.agent.current_request = None
            self.agent.pickup_location = None
            self.agent.destination_location = None
            self.agent.passenger_jid = None
            self.agent.just_finished_ride = True

            self.set_next_state("WAIT")

    async def setup(self):
        print(Fore.BLUE + f"Taxi Agent {self.name} started")

        fsm = self.TaxiFSM()

        fsm.add_state("WAIT", self.WaitState(), initial=True)
        fsm.add_state("PROPOSE", self.ProposeState())
        fsm.add_state("WAIT_RESPONSE", self.WaitResponseState())
        fsm.add_state("MOVE_TO_PICKUP", self.MoveToPickupState())
        fsm.add_state("MOVE_TO_DESTINATION", self.MoveToDestinationState())
        fsm.add_state("ARRIVED", self.ArrivedState())

        fsm.add_transition("WAIT", "WAIT")
        fsm.add_transition("WAIT", "PROPOSE")
        fsm.add_transition("PROPOSE", "WAIT_RESPONSE")
        fsm.add_transition("WAIT_RESPONSE", "MOVE_TO_PICKUP")
        fsm.add_transition("WAIT_RESPONSE", "WAIT")
        fsm.add_transition("MOVE_TO_PICKUP", "MOVE_TO_DESTINATION")
        fsm.add_transition("MOVE_TO_DESTINATION", "ARRIVED")
        fsm.add_transition("ARRIVED", "WAIT")

        self.add_behaviour(fsm)