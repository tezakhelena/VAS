import os
import asyncio
from agents.passenger_agent import PassengerAgent
from agents.taxi_agent import TaxiAgent
import random

# os.environ["SPADE_XMPP_USE_TLS"] = "false"
# os.environ["SPADE_XMPP_FORCE_STARTTLS"] = "false"

async def main():
    taxi1_location = (random.randint(0, 100), random.randint(0, 100))
    taxi2_location = (random.randint(0, 100), random.randint(0, 100))
    taxi3_location = (random.randint(0, 100), random.randint(0, 100))

    taxi1 = TaxiAgent("taxi1@localhost", "taxi1", location=taxi1_location)
    taxi2 = TaxiAgent("taxi2@localhost", "taxi2", location=taxi2_location)
    taxi3 = TaxiAgent("taxi3@localhost", "taxi3", location=taxi3_location)

    passenger1 = PassengerAgent("putnik@localhost", "putnik")
    passenger2 = PassengerAgent("putnik2@localhost", "putnik2")
    passenger3 = PassengerAgent("putnik3@localhost", "putnik3")

    await taxi1.start()
    await taxi2.start()
    await taxi3.start()

    while not all([taxi1.is_alive(), taxi2.is_alive(), taxi3.is_alive()]):
        await asyncio.sleep(1)

    await passenger1.start()
    await passenger2.start()
    await passenger3.start()

    while any([passenger1.is_alive(), passenger2.is_alive(), passenger3.is_alive()]):
        await asyncio.sleep(1)

    await asyncio.sleep(2)

    await taxi1.stop()
    await taxi2.stop()
    await taxi3.stop()

    print("All agents stopped.")

if __name__ == "__main__":
    asyncio.run(main())