#!/usr/bin/env python3
"""
PyUERANSIM CLI - 5G SA gNB and UE Simulator

Usage:
    py5gsim serve --port 8080              # Start web UI only
    py5gsim gnb --config gnb.yaml           # Run gNB with config file
    py5gsim ue --config ue.yaml             # Run UE with config file
    py5gsim all --gnb-config gnb.yaml --ue-config ue.yaml  # Run both
"""

import argparse
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def cmd_serve(args):
    """Start the web server."""
    from pyueransim.server import create_app
    import uvicorn

    app = create_app()

    print(f"Starting PyUERANSIM server on port {args.port}...")
    print(f"Access the UI at http://localhost:{args.port}")

    uvicorn.run(app, host="0.0.0.0", port=args.port)


def cmd_gnb(args):
    """Run gNB simulation connecting to real AMF."""
    from pyueransim.simulation import GnbSimulation
    from pyueransim.core.ngap import NgapConnection

    config = GnbConfig(
        mcc=args.mcc or "208",
        mnc=args.mnc or "93",
        nci=args.nci or 0x000000010,
        id_length=args.id_length or 32,
        tac=args.tac or 1,
        ngap_ip=args.local_ip or "127.0.0.1",
        gtp_ip=args.local_ip or "127.0.0.1",
        amf_ip=args.amf_host or "127.0.0.1",
        amf_port=args.amf_port or 38412
    )

    gnb_id = f"gnb-{os.getpid()}"
    gnb = GnbSimulation(config, gnb_id)

    async def run():
        print(f"Starting gNB: {gnb_id}")
        print(f"Connecting to AMF: {args.amf_host}:{args.amf_port}")
        print(f"Local IP: {args.local_ip or '127.0.0.1'}")

        try:
            await gnb.start()
            print("gNB is ready. Press Ctrl+C to stop.")

            # Keep running
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down gNB...")
        finally:
            await gnb.stop()

    asyncio.run(run())


def cmd_ue(args):
    """Run UE simulation connecting to real gNB."""
    from pyueransim.simulation import UeSimulation

    config = UeConfig(
        imsi=args.imsi or "imsi-208930000000001",
        key=args.key or "8baf473f2f8fd09487cccbd7097c6862",
        opc=args.opc or "8e27b6af0e692e750f32667a3b14605d",
        amf=args.amf or "8000",
        dnn=args.dnn or "internet",
        sst=args.sst or 1,
        sd=args.sd or 0x010203
    )

    ue_id = f"ue-{os.getpid()}"
    ue = UeSimulation(config, ue_id)

    async def run():
        print(f"Starting UE: {ue_id}")
        print(f"Connecting to gNB: {args.gnb_ip}")

        try:
            await ue.start(args.gnb_ip)
            print("UE is ready. Press Ctrl+C to stop.")

            # Keep running
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down UE...")

    asyncio.run(run())


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="PyUERANSIM - Python port of UERANSIM 5G SA Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    py5gsim serve --port 8080             # Start web UI server
    py5gsim gnb --amf-host 127.0.0.1      # Run gNB connecting to AMF
    py5gsim ue --gnb-ip 127.0.0.1         # Run UE connecting to gNB

For more information, visit: https://github.com/aligungr/UERANSIM/
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start web UI server")
    serve_parser.add_argument("--port", type=int, default=8080, help="Web server port (default: 8080)")
    serve_parser.set_defaults(func=cmd_serve)

    # gNB command
    gnb_parser = subparsers.add_parser("gnb", help="Run gNB simulation")
    gnb_parser.add_argument("--amf-host", default="127.0.0.1", help="AMF IP address")
    gnb_parser.add_argument("--amf-port", type=int, default=38412, help="AMF port")
    gnb_parser.add_argument("--local-ip", default="127.0.0.1", help="Local IP address")
    gnb_parser.add_argument("--mcc", help="Mobile Country Code")
    gnb_parser.add_argument("--mnc", help="Mobile Network Code")
    gnb_parser.add_argument("--nci", type=int, help="NR Cell Identity")
    gnb_parser.add_argument("--id-length", type=int, help="gNB ID length in bits")
    gnb_parser.add_argument("--tac", type=int, help="Tracking Area Code")
    gnb_parser.set_defaults(func=cmd_gnb)

    # UE command
    ue_parser = subparsers.add_parser("ue", help="Run UE simulation")
    ue_parser.add_argument("--gnb-ip", default="127.0.0.1", help="gNB IP address")
    ue_parser.add_argument("--imsi", help="IMSI")
    ue_parser.add_argument("--key", help="Subscription key (hex)")
    ue_parser.add_argument("--opc", help="OPC (hex)")
    ue_parser.add_argument("--amf", help="Authentication Management Field")
    ue_parser.add_argument("--dnn", default="internet", help="DNN/APN")
    ue_parser.add_argument("--sst", type=int, default=1, help="S-NSSAI SST")
    ue_parser.add_argument("--sd", type=int, default=0x010203, help="S-NSSAI SD")
    ue_parser.set_defaults(func=cmd_ue)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
