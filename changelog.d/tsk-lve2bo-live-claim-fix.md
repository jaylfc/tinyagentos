### Fixed

- Fix the claim fallback to properly handle live owner claims by writing `<pid> <boot_id>` to the claim file and only reclaiming when the owner is definitively dead on the same boot.
  
  The previous implementation had a race condition where a loser could preemptively unlink a live owner's claim, leading to cases where callers (`tinyagentos.secrets`, `tinyagentos.hub.identity`) could hold bytes that don't survive a restart.
  
  The fix ensures:
  1. The claim file contains `<pid> <boot_id>` when created
  2. A loser only reclaims the claim when the owner is definitively dead (kill(pid,0) -> ESRCH) OR when the boot ID differs
  3. If the owner is alive and on the same boot, the claim is preserved and the loser continues waiting
  4. This prevents the scenario where a live-but-slow winner (between taking the claim and `atomic_write_bytes` replacing the target) is preempted, and the original writer ends up with bytes that don't survive restart.