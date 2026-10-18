import os, sys, runpy
HARNESS = os.environ["AUDIT_HARNESS"]
sys.path.insert(0, HARNESS)
import fake_net
fake_net.install()
if not getattr(fake_net, "_seeded", False):
    import importlib
    seed_daten = importlib.import_module(os.environ.get("AUDIT_SEED", "seed_daten"))  # UX-Durchgang: AUDIT_SEED=seed_ux
    seed_daten.seed(fake_net)
    fake_net._seeded = True
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py"), run_name="__main__")
