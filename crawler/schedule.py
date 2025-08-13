from __future__ import annotations

import os
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

from . import fetch_feeds


def run_job() -> None:
	print(f"[crawler] {datetime.utcnow().isoformat()}Z: start fetch")
	try:
		fetch_feeds.main()
		print(f"[crawler] {datetime.utcnow().isoformat()}Z: done")
	except Exception as e:
		print(f"[crawler] {datetime.utcnow().isoformat()}Z: error {e}")


def main() -> None:
	interval_minutes = int(os.getenv("CRAWL_INTERVAL_MINUTES", "15"))
	scheduler = BlockingScheduler()
	scheduler.add_job(
		run_job,
		"interval",
		minutes=interval_minutes,
		coalesce=True,
		max_instances=1,
		misfire_grace_time=120,
	)
	print(f"[crawler] scheduling every {interval_minutes} minutes; BACKEND_URL={os.getenv('BACKEND_URL', 'http://127.0.0.1:5050')}")
	run_job()
	scheduler.start()


if __name__ == "__main__":
	main()
