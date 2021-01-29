# OnDemandMinecraft

Web service that spins up an EC2 instance to host a minecraft server.

This is to be paired with a seperate flask server that runs on the EC2 instance, which calls back to this to shut itself down when no-one is online.
