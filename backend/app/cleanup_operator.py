"""OS-authorized operator CLI; inspect is sanitized and requeue defaults dry-run."""
import argparse
import getpass
import json
import sys
import uuid

from app.core.database import SessionLocal
from app.services.cleanup_operations import inspect_job, requeue_job


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["inspect", "requeue"])
    parser.add_argument("job_id", type=uuid.UUID)
    parser.add_argument("--ticket", help="Non-secret incident/ticket identifier")
    parser.add_argument("--apply", action="store_true", help="Commit requeue; default is dry-run")
    args = parser.parse_args(argv)
    if args.operation == "requeue" and not args.ticket:
        parser.error("requeue requires --ticket")
    try:
        with SessionLocal() as db:
            if args.operation == "inspect":
                result = inspect_job(db, args.job_id)
            else:
                result = requeue_job(db, args.job_id, operator=getpass.getuser(), ticket=args.ticket, apply=args.apply)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        # Do not include arbitrary DB/OS/SDK exception strings in operator output.
        print(json.dumps({"error": "operator_command_failed", "error_type": type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
