import subprocess
def run_payload():
    return subprocess.run(["touch", "SHOULD_NOT_EXIST"])
