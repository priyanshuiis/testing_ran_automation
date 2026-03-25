import importlib.util
import platform
import subprocess
import sys
import time
import os
import json
from dotenv import load_dotenv
import paramiko
import re
import sys, io

# Force stdout/stderr to use UTF-8 encoding even on Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# -----------------------------
# Ensure required packages installed
# -----------------------------
for package_name, pip_name in [("paramiko", "paramiko"), ("dotenv", "python-dotenv")]:
    if importlib.util.find_spec(package_name) is None:
        print(f"{package_name} not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

REMOTE_HOST = os.getenv("RAN_REMOTE_HOST")
USERNAME = os.getenv("RAN_USERNAME")
PASSWORD = os.getenv("RAN_PASSWORD")
DOCKER_PROJECT_PATH = os.getenv("RAN_DOCKER_PROJECT", "~/gnb-docker")  # default path
INTERFACE = os.getenv("INTERFACE", "")

# VF / fronthaul configuration
FH_INTERFACE   = os.getenv("FH_INTERFACE")          
FH_MAC_1       = os.getenv("FH_MAC_1")
FH_MAC_2       = os.getenv("FH_MAC_2")
FH_CU_VLAN     = os.getenv("FH_CU_VLAN")
FH_MTU         = os.getenv("FH_MTU")
VF_SCRIPT_PATH = os.getenv("VF_SCRIPT_PATH")

if not REMOTE_HOST or not USERNAME or not PASSWORD:
    print("[ERROR] Missing required environment variables (RAN_REMOTE_HOST, RAN_USERNAME, RAN_PASSWORD).")
    sys.exit(1)

print("REMOTE_HOST:", REMOTE_HOST)
print("USERNAME:", USERNAME)
print("PASSWORD:", PASSWORD)


# -----------------------------
# Configuration
# -----------------------------
# Services – dynamically attach @FH_INTERFACE for ptp4l and phc2sys
SERVICES = [
    f"ptp4l@{FH_INTERFACE}" if FH_INTERFACE else "ptp4l",
    f"phc2sys@{FH_INTERFACE}" if FH_INTERFACE else "phc2sys",
    #"isc-dhcp-server",
    "tuned"
]

# Routes – load from env (JSON format)
routes_env = os.getenv("RAN_ROUTES", "[]")
try:
    ROUTES = json.loads(routes_env)
except json.JSONDecodeError:
    print("[ERROR] Failed to parse RAN_ROUTES from .env, falling back to empty list.")
    ROUTES = []

# -----------------------------
# Paramiko helpers
# -----------------------------
def run_cmd(ssh, cmd, use_pty=False, sudo=False, timeout=None):
    if sudo and not cmd.strip().startswith("sudo"):
        cmd = "sudo -S " + cmd

    if use_pty:
        stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True, timeout=timeout)
    else:
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)

    if sudo:
        try:
            stdin.write(PASSWORD + "\n")
            stdin.flush()
        except Exception:
            pass

    out = stdout.read().decode(errors="ignore")
    err = stderr.read().decode(errors="ignore")
    exit_status = stdout.channel.recv_exit_status()
    return out, err, exit_status

# -----------------------------
# Service management functions
# -----------------------------
def check_service_status(ssh, service):
    try:
        out, err, _ = run_cmd(ssh, f"systemctl is-failed {service}")
        if out.strip() == "failed":
            return "failed"
        out, err, _ = run_cmd(ssh, f"systemctl is-active {service}")
        return out.strip()
    except Exception as e:
        print(f"[ERROR] Exception while checking status of {service}: {e}")
        return "unknown"

def restart_service(ssh, service):
    try:
        _, _, _ = run_cmd(ssh, f"systemctl restart {service}", sudo=True, use_pty=True)
        print(f"[INFO] Restart command sent for {service}.")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to restart {service}: {e}")
        return False

def wait_for_service_active(ssh, service, timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        if check_service_status(ssh, service) == "active":
            return True
        time.sleep(2)
    return False

def check_and_recover(ssh, service):
    print(f"\n[CHECK] Checking status of {service}...")
    status = check_service_status(ssh, service)
    if status == "active":
        print(f"[OK] {service} is active.")
        return True
    print(f"[WARNING] {service} is not active (status: {status}). Attempting restart...")
    if restart_service(ssh, service):
        if wait_for_service_active(ssh, service):
            print(f"[RECOVERED] {service} is now active after restart.")
            return True
        else:
            print(f"[FAIL] {service} failed to recover. Current status: {check_service_status(ssh, service)}")
    else:
        print(f"[FAIL] Restart command failed for {service}.")
    return False

# -----------------------------
# VF & Interface functions
# -----------------------------
def get_interfaces_with_ips(ssh, ip_pattern="192.168."):
    try:
        out, err, _ = run_cmd(ssh, "ip -o addr show")
        interfaces = {}
        for line in out.strip().splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            iface = parts[1]
            if "inet" in parts:
                try:
                    ip = parts[3].split("/")[0]
                except Exception:
                    continue
                if ip.startswith(ip_pattern):
                    interfaces.setdefault(iface, []).append(ip)
        return interfaces
    except Exception as e:
        print(f"[ERROR] Failed to list interfaces: {e}")
        return {}

def check_virtual_functions(ssh, interface):
    try:
        stdin, stdout, stderr = ssh.exec_command(f"ip link show {interface}")
        output = stdout.read().decode()
        vfs = [line for line in output.splitlines() if line.strip().startswith("vf ")]
        if vfs:
            print(f"[INFO] Virtual functions found on {interface}:")
            for vf in vfs:
                print(" ", vf.strip())
            return True
        else:
            print(f"[INFO] No virtual functions found on {interface}.")
            return False
    except Exception as e:
        print(f"[ERROR] Failed to check VFs on {interface}: {e}")
        return False

def create_virtual_functions(ssh, interface, script_path):
    print(f"[ACTION] No VFs on {interface}. Attempting VF creation via: {script_path}")
    try:
        cmd = (
            f"bash -c 'cd {os.path.dirname(script_path)} && "
            f"sudo -S {script_path} "
            f"--interface {interface} "
            f"--mac1 {FH_MAC_1} --mac2 {FH_MAC_2} "
            f"--vlan {FH_CU_VLAN} --mtu {FH_MTU}'"
        )
        stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
        stdin.write(PASSWORD + "\n")
        stdin.flush()

        out = stdout.read().decode()
        err = stderr.read().decode()
        if out.strip():
            print("[VF-SCRIPT-OUT]\n" + out.strip())
        if err.strip():
            print("[VF-SCRIPT-ERR]\n" + err.strip())

        exit_status = stdout.channel.recv_exit_status()
        print(f"[INFO] VF script exit status: {exit_status}")
        return exit_status == 0
    except Exception as e:
        print(f"[ERROR] Failed to execute VF script: {e}")
        return False

def ensure_vfs(ssh, interface, script_path):
    print(f"\n[CHECK] Checking VFs on FH interface: {interface}")
    if check_virtual_functions(ssh, interface):
        return True

    if create_virtual_functions(ssh, interface, script_path):
        print(f"[VERIFY] Re-checking VFs on {interface}...")
        if check_virtual_functions(ssh, interface):
            print(f"[SUCCESS] VFs created successfully on {interface}.")
            return True
        else:
            print(f"[FAIL] VF creation did not succeed. Please inspect NIC/driver state.")
            return False
    else:
        print(f"[FAIL] VF creation script failed.")
        return False

def check_all_vfs_for_192_ips(ssh):
    interfaces = get_interfaces_with_ips(ssh)
    if not interfaces:
        print("[INFO] No interfaces with IPs in 192.168.*.* range found.")
        return
    for iface, ips in interfaces.items():
        print(f"\n[INFO] Checking interface {iface} with IP(s): {', '.join(ips)}")
        check_virtual_functions(ssh, iface)

# -----------------------------
# Route management functions
# -----------------------------
def check_and_add_routes(ssh, routes):
    all_present = True
    for route in routes:
        network = route["network"]
        via = route["via"]
        try:
            out, err, _ = run_cmd(ssh, f"ip route show {network}")
            output = out.strip()
            if output and via in output:
                print(f"[OK] Route {network} via {via} already exists.")
            else:
                _, err, _ = run_cmd(ssh, f"ip route add {network} via {via}", sudo=True, use_pty=True)
                print(f"[INFO] Added route {network} via {via}.")
        except Exception as e:
            print(f"[ERROR] Failed to check/add route {network} via {via}: {e}")
            all_present = False
    return all_present

# -----------------------------
# gNB and gNB components logs
# -----------------------------
def bring_up_gnb(ssh, project_path):
    print(f"\n[INFO] Bringing up gNB from {project_path} ...")
    try:
        cmd = f"cd {project_path} && sudo -S docker compose up -d"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        stdin.write(PASSWORD + "\n")
        stdin.flush()
        out = stdout.read().decode()
        err = stderr.read().decode()
        if out.strip(): print("[DOCKER-OUT]", out.strip())
        if err.strip(): print("[DOCKER-ERR]", err.strip())
        print("[INFO] gNB bring-up command executed.")
    except Exception as e:
        print(f"[ERROR] Failed to bring up gNB: {e}")

def check_cucp_logs(ssh, wait_time=10):
    print(f"[INFO] Waiting {wait_time}s for logs to populate...")
    time.sleep(wait_time)
    out, err, _ = run_cmd(ssh, "docker logs gnb-cucp", sudo=True, use_pty=True)
    logs = out
    match = re.search(r"Received NGSetupResponse from AMF", logs)
    if match:
        print(f"[OK] CUCP Log found:\n{match.group(0)}")
        return True
    else:
        print("[WARNING] CUCP log not found after waiting.")
        sys.exit(3)

def check_cuup_logs(ssh, wait_time=10):
    print(f"[INFO] Waiting {wait_time}s for logs to populate...")
    time.sleep(wait_time)
    out, err, _ = run_cmd(ssh, "docker logs gnb-cuup", sudo=True, use_pty=True)
    logs = out
    match = re.search(r"E1 connection established", logs)
    if match:
        print(f"[OK] CUUP Log found:\n{match.group(0)}")
        return True
    else:
        print("[WARNING] CUUP log not found after waiting.")
        sys.exit(3)

def check_du_logs(ssh, wait_time=10):
    print(f"[INFO] Waiting {wait_time}s for logs to populate...")
    time.sleep(wait_time)
    out, err, _ = run_cmd(ssh, "docker logs gnb-du", sudo=True, use_pty=True)
    logs = out
    match = re.search(r"Frame.Slot", logs)
    if match:
        print(f"[OK] DU Log found:\n{match.group(0)}")
        return True
    else:
        print("[WARNING] DU log not found after waiting.")
        sys.exit(3)

# -----------------------------
# Main script
# -----------------------------
if __name__ == "__main__":
    print(f"Detected OS: {platform.system().lower()}")
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(REMOTE_HOST, username=USERNAME, password=PASSWORD, timeout=10)
        print(f"\n[INFO] Connected to {REMOTE_HOST} as {USERNAME}")

        # 0. Ensure FH VFs exist (uses FH_INTERFACE, not INTERFACE)
        if FH_INTERFACE:
            vfs_ok = ensure_vfs(ssh, FH_INTERFACE, VF_SCRIPT_PATH)
        else:
            print("[SKIP] No FH_INTERFACE defined in .env, skipping VF check.")
            vfs_ok = True

        if not vfs_ok:
            print("\n[ABORT] VF creation/verification failed. Skipping bring-up.")
            sys.exit(2)

        # (Optional) show any 192.168.*.* interfaces + VF info
        check_all_vfs_for_192_ips(ssh)  # optional – can remove

        # 1. Check and recover services
        all_services_ok = True
        for svc in SERVICES:
            if not check_and_recover(ssh, svc):
                all_services_ok = False

        # 2. Check and add routes
        routes_ok = check_and_add_routes(ssh, ROUTES)

        # 3. Bring up gNB and verify component logs
        if all_services_ok and routes_ok:
            print("\n[INFO] All services are active and routes are present. Proceeding with gNB bring-up...")
            bring_up_gnb(ssh, DOCKER_PROJECT_PATH)
            check_cucp_logs(ssh, wait_time=3)
            check_cuup_logs(ssh, wait_time=3)
            check_du_logs(ssh, wait_time=5)
        else:
            print("\n[ABORT] Not all services/routes are OK. Skipping gNB bring-up.")

    except Exception as e:
        print(f"[ERROR] SSH connection failed: {e}")
        sys.exit(3)
    finally:
        try:
            ssh.close()
        except Exception:
            pass
        print("\n[INFO] SSH connection closed.")