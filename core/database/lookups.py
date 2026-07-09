"""
core/database/lookups.py
─────────────────────────
Static reference data for CIS Controls v8 and MITRE ATT&CK.
Used by Framework Intelligence, Risk Detail, and the Register display.
No database queries — pure data lookup.
"""

# ── CIS Controls v8 — complete titles and descriptions ───────────────────────

CIS_CONTROL_DATA = {
    "CIS-1": {
        "title":   "Inventory and Control of Enterprise Assets",
        "desc":    "Actively manage all enterprise assets connected to the infrastructure.",
        "ig":      "IG1",
        "color":   "#1565C0",
    },
    "CIS-2": {
        "title":   "Inventory and Control of Software Assets",
        "desc":    "Actively manage all software on the network so only authorised software is installed.",
        "ig":      "IG1",
        "color":   "#1565C0",
    },
    "CIS-3": {
        "title":   "Data Protection",
        "desc":    "Develop processes to identify, classify, handle, retain and dispose of data securely.",
        "ig":      "IG1",
        "color":   "#1565C0",
    },
    "CIS-4": {
        "title":   "Secure Configuration of Enterprise Assets and Software",
        "desc":    "Establish and maintain the secure configuration of enterprise assets and software.",
        "ig":      "IG1",
        "color":   "#1565C0",
    },
    "CIS-5": {
        "title":   "Account Management",
        "desc":    "Use processes and tools to assign and manage authorisation to credentials for user accounts.",
        "ig":      "IG1",
        "color":   "#1565C0",
    },
    "CIS-6": {
        "title":   "Access Control Management",
        "desc":    "Use processes and tools to create, assign, manage and revoke access credentials and privileges.",
        "ig":      "IG1",
        "color":   "#1565C0",
    },
    "CIS-7": {
        "title":   "Continuous Vulnerability Management",
        "desc":    "Develop a plan to continuously assess and track vulnerabilities on all enterprise assets.",
        "ig":      "IG1",
        "color":   "#2E7D32",
    },
    "CIS-8": {
        "title":   "Audit Log Management",
        "desc":    "Collect, alert, review and retain audit logs to detect, understand or recover from an attack.",
        "ig":      "IG1",
        "color":   "#2E7D32",
    },
    "CIS-9": {
        "title":   "Email and Web Browser Protections",
        "desc":    "Improve protections and detections of threats from email and web vectors.",
        "ig":      "IG1",
        "color":   "#2E7D32",
    },
    "CIS-10": {
        "title":   "Malware Defenses",
        "desc":    "Prevent or control the installation, spread and execution of malicious applications.",
        "ig":      "IG1",
        "color":   "#2E7D32",
    },
    "CIS-11": {
        "title":   "Data Recovery",
        "desc":    "Establish and maintain data recovery practices sufficient to restore in-scope assets.",
        "ig":      "IG1",
        "color":   "#2E7D32",
    },
    "CIS-12": {
        "title":   "Network Infrastructure Management",
        "desc":    "Establish, implement and actively manage network devices to prevent attackers from exploiting services.",
        "ig":      "IG2",
        "color":   "#E65100",
    },
    "CIS-13": {
        "title":   "Network Monitoring and Defense",
        "desc":    "Operate processes and tooling to establish and maintain comprehensive network monitoring.",
        "ig":      "IG2",
        "color":   "#E65100",
    },
    "CIS-14": {
        "title":   "Security Awareness and Skills Training",
        "desc":    "Establish and maintain a security awareness programme to influence behaviour.",
        "ig":      "IG1",
        "color":   "#1565C0",
    },
    "CIS-15": {
        "title":   "Service Provider Management",
        "desc":    "Develop a process to evaluate service providers who hold sensitive data or are responsible for IT.",
        "ig":      "IG2",
        "color":   "#E65100",
    },
    "CIS-16": {
        "title":   "Application Software Security",
        "desc":    "Manage the security lifecycle of in-house developed, hosted or acquired software.",
        "ig":      "IG2",
        "color":   "#E65100",
    },
    "CIS-17": {
        "title":   "Incident Response Management",
        "desc":    "Establish a programme to develop and maintain an incident response capability.",
        "ig":      "IG2",
        "color":   "#E65100",
    },
    "CIS-18": {
        "title":   "Penetration Testing",
        "desc":    "Test the effectiveness and resiliency of enterprise assets through identifying and exploiting weaknesses.',",
        "ig":      "IG3",
        "color":   "#6A1B9A",
    },
    "Not Applicable": {
        "title":   "Not Applicable",
        "desc":    "No CIS Control mapped to this risk.",
        "ig":      "—",
        "color":   "#3E4A5A",
    },
}

IG_COLORS = {
    "IG1": "#1565C0",
    "IG2": "#E65100",
    "IG3": "#6A1B9A",
    "—":   "#3E4A5A",
}


def get_cis_info(cis_key: str) -> dict:
    """Return full CIS control info for a key like 'CIS-5'."""
    return CIS_CONTROL_DATA.get(
        cis_key,
        {"title": cis_key, "desc": "", "ig": "—", "color": "#3E4A5A"})


def cis_display(cis_key: str) -> str:
    """Return formatted display string: 'CIS-5 · Account Management'"""
    if not cis_key or cis_key == "Not Applicable":
        return "Not Applicable"
    info = get_cis_info(cis_key)
    return f"{cis_key}  ·  {info['title']}"


# ── MITRE ATT&CK — tactics with descriptions and common techniques ────────────

MITRE_TACTIC_DATA = {
    "Reconnaissance": {
        "id":    "TA0043",
        "desc":  "Gathering information to plan future adversary operations.",
        "color": "#B71C1C",
        "techniques": [
            ("T1595", "Active Scanning", "Scanning victim infrastructure for information."),
            ("T1592", "Gather Victim Host Information", "Info about victim hosts including OS, IP, hardware."),
            ("T1589", "Gather Victim Identity Information", "Email addresses, names, usernames."),
            ("T1590", "Gather Victim Network Information", "Network topology, IPs, domain names."),
            ("T1591", "Gather Victim Org Information", "Information about the target organisation."),
        ],
        "detections": [
            "Monitor for unusual inbound scanning activity",
            "Alert on probing of external attack surface",
            "Review web server access logs for enumeration patterns",
        ],
        "mitigations": [
            "Limit public exposure of infrastructure details",
            "Use honeypots to detect scanning activity",
            "Monitor DNS queries for unusual enumeration",
        ],
    },
    "Resource Development": {
        "id":    "TA0042",
        "desc":  "Establishing resources to support operations (infrastructure, accounts, capabilities).",
        "color": "#B71C1C",
        "techniques": [
            ("T1583", "Acquire Infrastructure", "Acquiring infrastructure for use in targeting."),
            ("T1584", "Compromise Infrastructure", "Compromising third-party infrastructure."),
            ("T1585", "Establish Accounts", "Creating accounts for use in targeting."),
            ("T1587", "Develop Capabilities", "Building capabilities to use in an operation."),
        ],
        "detections": [
            "Monitor for newly registered domains similar to your organisation",
            "Track infrastructure associated with known threat actors",
        ],
        "mitigations": [
            "Register similar domain names preemptively",
            "Participate in threat intelligence sharing",
        ],
    },
    "Initial Access": {
        "id":    "TA0001",
        "desc":  "Gaining an initial foothold within a network.",
        "color": "#B71C1C",
        "techniques": [
            ("T1566", "Phishing", "Sending phishing messages to gain access."),
            ("T1190", "Exploit Public-Facing Application", "Exploiting internet-facing applications."),
            ("T1133", "External Remote Services", "Abusing VPNs, RDP, and other remote services."),
            ("T1078", "Valid Accounts", "Using compromised credentials."),
            ("T1195", "Supply Chain Compromise", "Manipulating products or delivery mechanisms."),
        ],
        "detections": [
            "Monitor email gateways for phishing indicators",
            "Alert on new external connections to remote services",
            "Review authentication logs for unusual login patterns",
        ],
        "mitigations": [
            "Implement email filtering and anti-phishing controls",
            "Enforce MFA on all external-facing services",
            "Maintain a patching cadence for public-facing applications",
        ],
    },
    "Execution": {
        "id":    "TA0002",
        "desc":  "Running adversary-controlled code on a local or remote system.",
        "color": "#B71C1C",
        "techniques": [
            ("T1059", "Command and Scripting Interpreter", "Using interpreters like PowerShell, bash, Python."),
            ("T1053", "Scheduled Task/Job", "Abusing task schedulers to execute code."),
            ("T1204", "User Execution", "Tricking users into executing malicious files."),
        ],
        "detections": [
            "Monitor for unusual script execution (PowerShell, WScript)",
            "Alert on new scheduled tasks created by non-admin users",
            "Deploy endpoint detection for process injection",
        ],
        "mitigations": [
            "Restrict scripting language execution via AppLocker",
            "Enable enhanced PowerShell logging",
            "Train users to identify and report suspicious files",
        ],
    },
    "Persistence": {
        "id":    "TA0003",
        "desc":  "Maintaining access across restarts, credential changes and interruptions.",
        "color": "#B71C1C",
        "techniques": [
            ("T1098", "Account Manipulation", "Manipulating accounts to maintain access."),
            ("T1136", "Create Account", "Creating new accounts to maintain access."),
            ("T1543", "Create or Modify System Process", "Creating/modifying launch agents/daemons."),
            ("T1053", "Scheduled Task/Job", "Using task schedulers for persistence."),
        ],
        "detections": [
            "Monitor for new local accounts or group membership changes",
            "Alert on modifications to startup folders or registry run keys",
            "Track new scheduled tasks",
        ],
        "mitigations": [
            "Restrict ability to create local accounts",
            "Monitor privileged group membership changes",
            "Implement Privileged Access Workstations",
        ],
    },
    "Privilege Escalation": {
        "id":    "TA0004",
        "desc":  "Gaining higher-level permissions on a system or network.",
        "color": "#B71C1C",
        "techniques": [
            ("T1548", "Abuse Elevation Control Mechanism", "Abusing mechanisms to gain elevated privileges."),
            ("T1068", "Exploitation for Privilege Escalation", "Exploiting software bugs to elevate privileges."),
            ("T1078", "Valid Accounts", "Using valid accounts to elevate privileges."),
        ],
        "detections": [
            "Monitor for UAC bypass attempts",
            "Alert on processes running with unexpected privileges",
            "Track use of known escalation exploits",
        ],
        "mitigations": [
            "Apply principle of least privilege across all accounts",
            "Keep systems patched to prevent exploit-based escalation",
            "Enforce credential guard on Windows endpoints",
        ],
    },
    "Defense Evasion": {
        "id":    "TA0005",
        "desc":  "Avoiding detection throughout the attack lifecycle.",
        "color": "#B71C1C",
        "techniques": [
            ("T1036", "Masquerading", "Manipulating name or location of executables."),
            ("T1070", "Indicator Removal", "Removing indicators of compromise."),
            ("T1027", "Obfuscated Files", "Making files/information difficult to discover."),
            ("T1562", "Impair Defenses", "Disabling security tools."),
        ],
        "detections": [
            "Alert on security tool process termination",
            "Monitor for log tampering or deletion",
            "Detect encoded script execution",
        ],
        "mitigations": [
            "Enable tamper protection on endpoint security tools",
            "Ship logs to a remote SIEM immediately",
            "Use application whitelisting",
        ],
    },
    "Credential Access": {
        "id":    "TA0006",
        "desc":  "Stealing credentials like account names and passwords.",
        "color": "#B71C1C",
        "techniques": [
            ("T1110", "Brute Force", "Attempting to guess credentials."),
            ("T1003", "OS Credential Dumping", "Dumping credentials from OS and software."),
            ("T1555", "Credentials from Password Stores", "Collecting credentials from password managers."),
            ("T1558", "Steal or Forge Kerberos Tickets", "Kerberoasting, Pass-the-Ticket."),
        ],
        "detections": [
            "Monitor for repeated authentication failures",
            "Alert on LSASS memory access by non-system processes",
            "Detect Kerberoasting patterns in event logs",
        ],
        "mitigations": [
            "Enforce MFA on all accounts",
            "Implement credential guard",
            "Use a Privileged Access Management solution",
        ],
    },
    "Discovery": {
        "id":    "TA0007",
        "desc":  "Understanding the environment to determine next steps.",
        "color": "#B71C1C",
        "techniques": [
            ("T1083", "File and Directory Discovery", "Enumerating files and directories."),
            ("T1046", "Network Service Discovery", "Enumerating network services."),
            ("T1069", "Permission Groups Discovery", "Finding group and permission information."),
            ("T1082", "System Information Discovery", "Enumerating OS and hardware information."),
        ],
        "detections": [
            "Monitor for unusual enumeration commands (net user, whoami, ipconfig)",
            "Alert on rapid internal network scanning",
        ],
        "mitigations": [
            "Limit information returned by internal DNS and LDAP queries",
            "Deploy deception technology to detect enumeration",
        ],
    },
    "Lateral Movement": {
        "id":    "TA0008",
        "desc":  "Moving through the environment to reach objectives.",
        "color": "#B71C1C",
        "techniques": [
            ("T1021", "Remote Services", "Using remote services like RDP, SMB, SSH."),
            ("T1550", "Use Alternate Authentication Material", "Pass-the-Hash, Pass-the-Ticket."),
            ("T1080", "Taint Shared Content", "Corrupting shared content to spread."),
        ],
        "detections": [
            "Monitor for unusual RDP or SMB connections between workstations",
            "Alert on pass-the-hash indicators",
            "Track service account usage across systems",
        ],
        "mitigations": [
            "Restrict lateral movement with micro-segmentation",
            "Enable Windows Firewall to block workstation-to-workstation SMB",
            "Implement Privileged Access Workstations",
        ],
    },
    "Collection": {
        "id":    "TA0009",
        "desc":  "Gathering data of interest to the adversary's goal.",
        "color": "#B71C1C",
        "techniques": [
            ("T1039", "Data from Network Shared Drive", "Collecting data from shared drives."),
            ("T1113", "Screen Capture", "Capturing screen contents."),
            ("T1005", "Data from Local System", "Searching local system for files of interest."),
        ],
        "detections": [
            "Alert on bulk file access from a single account",
            "Monitor for screen capture utilities",
            "Detect large data staging in temporary directories",
        ],
        "mitigations": [
            "Implement DLP controls on sensitive data stores",
            "Classify and restrict access to sensitive files",
        ],
    },
    "Command & Control": {
        "id":    "TA0011",
        "desc":  "Communicating with compromised systems to control them.",
        "color": "#B71C1C",
        "techniques": [
            ("T1071", "Application Layer Protocol", "Using protocols like HTTP/HTTPS for C2."),
            ("T1095", "Non-Application Layer Protocol", "Using protocols like ICMP for C2."),
            ("T1572", "Protocol Tunneling", "Tunneling C2 traffic within other protocols."),
        ],
        "detections": [
            "Monitor outbound DNS for high-frequency or long queries (DNS tunnelling)",
            "Alert on beaconing patterns in network traffic",
            "Detect unusual HTTPS traffic to new external destinations",
        ],
        "mitigations": [
            "Implement web proxy with SSL inspection",
            "Block non-essential outbound ports",
            "Use threat intelligence feeds to block known C2 infrastructure",
        ],
    },
    "Exfiltration": {
        "id":    "TA0010",
        "desc":  "Stealing data from the victim network.",
        "color": "#B71C1C",
        "techniques": [
            ("T1041", "Exfiltration Over C2 Channel", "Exfiltrating data over the C2 channel."),
            ("T1567", "Exfiltration Over Web Service", "Using cloud services (Dropbox, GitHub) for exfil."),
            ("T1048", "Exfiltration Over Alternative Protocol", "Using alternative protocols to evade detection."),
        ],
        "detections": [
            "Monitor for large outbound data transfers",
            "Alert on uploads to cloud storage services from endpoints",
            "Detect unusual traffic to external IP ranges",
        ],
        "mitigations": [
            "Implement egress filtering and DLP",
            "Block upload capabilities to personal cloud storage",
            "Monitor for unusually large DNS responses",
        ],
    },
    "Impact": {
        "id":    "TA0040",
        "desc":  "Disrupting availability or compromising integrity of systems and data.",
        "color": "#B71C1C",
        "techniques": [
            ("T1486", "Data Encrypted for Impact", "Encrypting data to interrupt availability (ransomware)."),
            ("T1490", "Inhibit System Recovery", "Deleting backups, shadow copies, recovery options."),
            ("T1499", "Endpoint Denial of Service", "Overwhelming endpoints to deny service."),
        ],
        "detections": [
            "Alert on mass file encryption events",
            "Monitor for deletion of shadow copies",
            "Detect unusual CPU/memory consumption indicating DoS",
        ],
        "mitigations": [
            "Maintain offline, immutable backups",
            "Protect shadow copies with additional access controls",
            "Deploy ransomware-specific endpoint detection",
        ],
    },
    "Not Applicable": {
        "id":    "—",
        "desc":  "No MITRE ATT&CK tactic mapped to this risk.",
        "color": "#3E4A5A",
        "techniques": [],
        "detections": [],
        "mitigations": [],
    },
}


def get_mitre_info(tactic: str) -> dict:
    """Return full MITRE tactic info."""
    return MITRE_TACTIC_DATA.get(
        tactic,
        {"id": "—", "desc": "", "color": "#3E4A5A",
         "techniques": [], "detections": [], "mitigations": []})


def mitre_display(tactic: str) -> str:
    """Return formatted display: 'TA0006 · Credential Access'"""
    if not tactic or tactic == "Not Applicable":
        return "Not Applicable"
    info = get_mitre_info(tactic)
    tid  = info.get("id", "")
    return f"{tid}  ·  {tactic}" if tid and tid != "—" else tactic
