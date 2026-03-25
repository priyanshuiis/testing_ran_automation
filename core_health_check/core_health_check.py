import importlib.util
import platform
import subprocess
import sys
import time
import os
import sys, io

# Force stdout/stderr to use UTF-8 encoding even on Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

#  Ensure paramiko installed
package_name = "paramiko"
if importlib.util.find_spec(package_name) is None:
    print(f"{package_name} not found. Installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])

# Ensure python-dotenv installed
package_name = "dotenv"   # not python-dotenv
if importlib.util.find_spec(package_name) is None:
    print("python-dotenv not found. Installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-dotenv"])


import paramiko
from dotenv import load_dotenv

#  MUST call this before os.getenv()
#load_dotenv(dotenv_path=r"c:\robot framework\demo\Robot\core_health_check\.env")
#load_dotenv(dotenv_path=r"c:\robot framework\demo\Robot\core_health_check\.env", override=True)
#load_dotenv(dotenv_path=r"C:\Tejas\robot framework\demo\core_health_check\.env", override=True)
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=env_path, override=True)

#  Fetch values from .env
REMOTE_HOST = os.getenv("REMOTE_HOST")
USERNAME = os.getenv("SYS_USERNAME")
PASSWORD = os.getenv("PASSWORD")
NAMESPACE = os.getenv("NAMESPACE")
RETRY_INTERVAL = int(os.getenv("RETRY_INTERVAL", "10"))
MAX_WAIT = int(os.getenv("MAX_WAIT", "120"))

# Debugging
print("REMOTE_HOST:", REMOTE_HOST)
print("USERNAME:", USERNAME)
print("PASSWORD:", PASSWORD)
print("NAMESPACE:", NAMESPACE)
print("RETRY_INTERVAL:", RETRY_INTERVAL)
print("MAX_WAIT:", MAX_WAIT)

if not REMOTE_HOST or not USERNAME or not PASSWORD:
    print("[ERROR] Missing required environment variables (RAN_REMOTE_HOST, RAN_USERNAME, RAN_PASSWORD).")
    sys.exit(1)



# Pod checking function using existing SSH session
def check_pods(ssh):
    
    cmd = f"bash -lc 'kubectl get pods -n {NAMESPACE}'"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    output = stdout.read().decode().strip()
    error_output = stderr.read().decode().strip()

    # 1 If kubectl not installed
    if "not found" in output.lower() or "not found" in error_output.lower():
        print("❌ kubectl not found on remote host! Please install kubectl.")
        ssh.close()
        sys.exit(1)

    lines = output.splitlines()

    # 2️ If no pods at all
    if len(lines) <= 1:  # only header present
        print(f"❌ No pods found in namespace '{NAMESPACE}'. Exiting...")
        ssh.close()
        sys.exit(1)

    # 3️ Normal case: parse pod statuses
    not_running = []
    running_pods = []
    for line in lines[1:]:  # skip header
        cols = line.split()
        pod_name = cols[0]
        status = cols[2]
        if status != "Running":
            not_running.append(pod_name)
        else:
            running_pods.append(pod_name)

    return not_running, running_pods



# Wait for all pods to be running
def wait_for_pods(ssh, max_wait=MAX_WAIT, retry_interval=RETRY_INTERVAL):
    start_time = time.time()
    while True:
        not_running, running_pods = check_pods(ssh)

        if not not_running:
            print("\n All the pods are running!")
            for pod in running_pods:
                print(pod)
            return

        elapsed = time.time() - start_time
        if elapsed >= max_wait:
            print("\n The following pods failed to reach 'Running' status within 2 minutes:")
            for pod in not_running:
                print("-", pod)
            print("Please check the pod logs or status manually on the remote host!")
            ssh.close()
            sys.exit(1)

        print("\n Some pods are not running:")
        for pod in not_running:
            print("-", pod)
        print(f"Retrying in {retry_interval} seconds... ({int(elapsed)}/{max_wait}s elapsed)\n")
        time.sleep(retry_interval)


# Get interface on remote
def get_interface_remote(ssh):
    stdin, stdout, stderr = ssh.exec_command(
        "ip route get 8.8.8.8 | awk '{for(i=1;i<=NF;i++){ if($i==\"dev\"){print $(i+1)}}}'"
    )
    interface = stdout.read().decode().strip()
    print(f"Active interface to internet on remote: {interface}")
    return interface


def check_and_disable_gro_remote(ssh, interface, password=None):
    stdin, stdout, stderr = ssh.exec_command(
        f"ethtool -k {interface} | grep generic-receive-offload"
    )
    gro_status = stdout.read().decode().strip().split(":")[-1].strip()
    
    if gro_status == "on":
        print("GRO is on. Turning off...")
        cmd = f"sudo -S ethtool -K {interface} gro off"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        if password:
            stdin.write(password + "\n")  # send sudo password
            stdin.flush()
        print(stdout.read().decode(), stderr.read().decode())
        print("GRO was on and is now turned off")
    else:
        print("GRO is already off ")


# Ensure MTU on remote
def ensure_mtu_remote(ssh, interface, desired_mtu=1410, password=None):
    stdin, stdout, stderr = ssh.exec_command(f"ifconfig {interface}")
    output = stdout.read().decode()
    mtu_line = next((line for line in output.splitlines() if "mtu" in line), None)
    
    if mtu_line:
        parts = mtu_line.split()
        mtu_index = parts.index('mtu') + 1
        current_mtu = int(parts[mtu_index])
        if current_mtu != desired_mtu:
            print(f"Current MTU is {current_mtu}, setting to {desired_mtu}...")
            cmd = f"sudo -S ip link set dev {interface} mtu {desired_mtu}"
            stdin, stdout, stderr = ssh.exec_command(cmd)
            stdin.write(password + "\n")   # send sudo password
            stdin.flush()
            print(stdout.read().decode(), stderr.read().decode())
            print(f"MTU updated to {desired_mtu}.")
        else:
            print(f"MTU is already {desired_mtu}, all good! ")
    else:
        print(f"Could not find MTU for {interface}.")








#  Verify core and access interfaces exist
def verify_core_and_access_interfaces(ssh):
    for iface_name in ["access", "core"]:
        stdin, stdout, stderr = ssh.exec_command(f"ifconfig {iface_name}")
        output = stdout.read().decode().strip()
        if output and iface_name in output:
            print(f" Interface '{iface_name}' is present on remote host.")
        else:
            print(f" Interface '{iface_name}' is NOT present. Exiting...")
            ssh.close()
            sys.exit(1)


#  Get UPF interface MACs and verify ARP
def get_upf_mac_and_verify_arp(ssh):
    print("\n--- Fetching `ip a` output from UPF container ---")
    stdin, stdout, stderr = ssh.exec_command(
        "kubectl exec -i upf-0 -n iosmcn -- ip a"
    )
    output = stdout.read().decode().strip()
    error_output = stderr.read().decode().strip()

    #  Error handling for common errors
    if "error:" in output.lower() or "error:" in error_output or "not found" in output.lower() or "not found" in error_output:
        print(f" Error accessing upf-0 container:\n{output}\n{error_output}")
        print(" Exiting script due to UPF container issue...")
        ssh.close()
        sys.exit(1)

    print(output)  # Debug output

    macs = {}
    current_iface = None
    for line in output.splitlines():
        line = line.strip()
        # Interface header
        if line and ":" in line and not line.startswith("link/"):
            parts = line.split(":")
            iface_name = parts[1].split("@")[0].strip()  # get "access" or "core"
            current_iface = iface_name
        # Capture MAC address
        elif "link/ether" in line and current_iface in ["access", "core"]:
            mac_address = line.split()[1]
            macs[current_iface] = mac_address
            current_iface = None

    if not macs:
        print(" Could not find access/core interfaces inside upf-0. Exiting...")
        ssh.close()
        sys.exit(1)

    print("\n Parsed MAC addresses:", macs)

    for iface_name, mac_address in macs.items():
        print(f"\n Checking ARP entry for '{iface_name}' with MAC '{mac_address}'...")
        stdin, stdout, stderr = ssh.exec_command(f"arp | grep {mac_address}")
        arp_output = stdout.read().decode().strip()

        if arp_output:
            print(f" Found ARP entry for {iface_name}: {arp_output}")
            if mac_address in arp_output:
                print(f" Confirmed MAC {mac_address} matches ARP entry for '{iface_name}' ")
            else:
                print(f" MAC mismatch in ARP output for '{iface_name}'!")
        else:
            print(f" No ARP entry found for '{iface_name}' with MAC '{mac_address}'!")


#  Main flow
if __name__ == "__main__":
    print(f"Detected OS: {platform.system().lower()}")

    #  Create one SSH connection for all remote commands
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(REMOTE_HOST, username=USERNAME, password=PASSWORD)

    wait_for_pods(ssh)  #  wait until all pods are up

    verify_core_and_access_interfaces(ssh)
    get_upf_mac_and_verify_arp(ssh)

    iface = get_interface_remote(ssh)
    check_and_disable_gro_remote(ssh, iface,PASSWORD)
    ensure_mtu_remote(ssh, iface, 1410, PASSWORD)

    ssh.close()