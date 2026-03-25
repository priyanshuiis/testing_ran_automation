# Robot_framework
This repository automates the workflow the bringing up of private 5g and start testing based on the test case list provided.

##  🧩Workflow Overview: Robot Automation Execution Flow
 
<p align="center">
  <img src="./pictures/Flowchart for v1.0_final.png" alt="Robot Scheduler Flowchart" width="400">
</p>

### 🧩 Process Steps Description

1. **Initialize Results Directory**  
   Create or set up the folder where all test case results will be stored.

2. **Perform Prechecks**  
   Run core and RAN health-check scripts.  
   Validate that the system is ready for test execution.

3. **Bring Up Dockerized RAN**  
   Start the required RAN services inside Docker containers.

4. **Authenticate via REST API**  
   Log into the server using API credentials.  
   Obtain an authentication token for further operations.

5. **Fetch Test Cases from Excel**  
   Read test case data sequentially from the Excel sheet.

6. **Execute Test Cases (Loop)**  
   For each test case:  
   - Run the test logic  
   - Capture the result (pass/fail, logs, etc.)  
   - Store the result in the initialized results directory

7. **Logout User**  
   Terminate the API session and clear credentials.

8. **End Process**


# 🤖 Robot Framework : User Guide 

A complete step-by-step guide to setting up and running Robot Framework with RPA libraries inside a Python virtual environment.

---

## 📚 Table of Contents
- [1️⃣ Install Python 3.11](#1️⃣-install-python-311)
- [2️⃣ Create a Virtual Environment](#2️⃣-create-a-virtual-environment)
- [3️⃣ Upgrade Core Python Tools](#3️⃣-upgrade-core-python-tools)
- [4️⃣ Install Robot Framework & RPA Dependencies](#4️⃣-install-robot-framework--rpa-dependencies)
- [5️⃣ Verify Installation](#5️⃣-verify-installation)
- [6️⃣ Troubleshooting](#6️⃣-troubleshooting)
- [7️⃣ Steps to Use Robot Framework](#7️⃣-steps-to-use-robot-framework)

---

## 1️⃣ Install Python 3.11

Download and install **Python 3.11 (64-bit)** from [python.org](https://www.python.org/)

**During installation:**
- ✅ Check “Add Python to PATH”
- ✅ Install **py launcher (py.exe)** for easier version switching

**Verify installation:**
```bash
py --version
py -3.11 --version
```

---

## 2️⃣ Create a Virtual Environment

Open PowerShell or Terminal and navigate to your project folder:
```bash
cd "<path-to-your-folder>"
```

**Create a virtual environment:**
```bash
py -3.11 -m venv <venv-name>
```

**Activate the virtual environment:**
```bash
<venv-name>\Scripts\activate   # Windows
source <venv-name>/bin/activate   # Linux/Mac
```

You should see the prefix:
```
(<venv-name>)
```
in your terminal prompt.

---

## 3️⃣ Upgrade Core Python Tools

Inside the virtual environment, upgrade pip, setuptools, and wheel:
```bash
python -m pip install --upgrade pip setuptools wheel
```

**Installed versions:**
- pip → 25.2  
- setuptools → 80.9.0  
- wheel → 0.45.1

---

## 4️⃣ Install Robot Framework & RPA Dependencies

Create a **requirements.txt** file to keep dependencies organized:
```text
robotframework==7.1.1
rpaframework==30.0.2
openpyxl>=3.1.5
playwright>=1.49.0
requests>=2.32.3
```

Install all dependencies at once:
```bash
pip install -r requirements.txt
```

This installs:
- **Robot Framework** (core test runner)
- **RPA Framework** (libraries for Excel, Browser, Files, HTTP, etc.)
- **OpenPyXL** (Excel support)
- **Playwright** (browser automation)
- **Requests** (API testing)

---

## 5️⃣ Verify Installation## ✅ Summary

| Step | Action | Command |
|------|---------|----------|
| 1 | Install Python 3.11 | `py -3.11 --version` |
| 2 | Create venv | `py -3.11 -m venv myenv` |
| 3 | Activate venv | `source myenv/bin/activate` |
| 4 | Install dependencies | `pip install -r requirements.txt` |
| 5 | Verify | `robot --version` |
| 6 | Troubleshoot | `certifi` / `trusted-host` |
| 7 | Run test | `robot iosmcn.robot` |

---


Check if all packages are installed correctly:
```bash
pip list
```

Check for dependency conflicts:
```bash
pip check
```

Run a sample Robot test:
```bash
robot --version
robot --help
```

---

## 6️⃣ Troubleshooting

If you encounter SSL certificate errors like:
```
SSLError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate
```

Upgrade the certificate bundle:
```bash
python -m pip install --upgrade certifi --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

Use `--trusted-host` flags to temporarily bypass SSL verification:
```bash
python -m pip install pip==25.2 setuptools==80.9.0 wheel==0.45.1 --trusted-host pypi.org --trusted-host files.pythonhosted.org
python -m pip install -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org
python -m pip install paramiko python-dotenv --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

---

## 7️⃣ Steps to Use Robot Framework

### 🧩 1. Update Environment Files
Add the required credentials and file paths to the `.env` files.  
Update `.env` in the following folders:
- `core_health_check`
- `ran_health_check`
- `robot`

Include appropriate values for:
- Username
- Password
- Excel file path
- Any other configuration variables

---

### 🧪 2. Run the Robot Framework Test
Execute the Robot Framework test file:
```bash
robot iosmcn.robot
```
