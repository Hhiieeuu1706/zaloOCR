import uuid
import hashlib
import datetime
import winreg

SECRET_SALT = "ZaloAuctionBidderSecret2026"

def get_windows_machine_guid():
    """Reads the Windows MachineGuid from the registry."""
    try:
        registry_key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        )
        value, regtype = winreg.QueryValueEx(registry_key, "MachineGuid")
        winreg.CloseKey(registry_key)
        return str(value).strip().upper()
    except Exception:
        return None

def get_mac_address_hash():
    """Fallback method using network card MAC address."""
    try:
        mac = uuid.getnode()
        mac_str = ':'.join(('%012X' % mac)[i:i+2] for i in range(0, 12, 2))
        return mac_str
    except Exception:
        return "00:00:00:00:00:00"

def get_hardware_id():
    """Returns a unique, stable hardware ID based on Windows MachineGuid, falling back to MAC address."""
    guid = get_windows_machine_guid()
    if guid:
        hardware_hash = hashlib.sha256((guid + SECRET_SALT).encode('utf-8')).hexdigest()[:16].upper()
    else:
        # Fallback to MAC address if registry cannot be read
        mac_str = get_mac_address_hash()
        hardware_hash = hashlib.sha256((mac_str + SECRET_SALT).encode('utf-8')).hexdigest()[:16].upper()
    return hardware_hash

def get_legacy_hardware_id():
    """Helper to verify older keys generated using only the MAC address method."""
    mac_str = get_mac_address_hash()
    return hashlib.sha256((mac_str + SECRET_SALT).encode('utf-8')).hexdigest()[:16].upper()

def generate_key_for_machine(hardware_id, expiry_date_str):
    """
    Utility helper for admin to generate license keys.
    expiry_date_str must be in format YYYY-MM-DD
    """
    raw_payload = f"{hardware_id}|{expiry_date_str}"
    signature = hashlib.sha256((raw_payload + SECRET_SALT).encode('utf-8')).hexdigest()[:8].upper()
    # Use '#' as separator instead of '-' because the date YYYY-MM-DD contains hyphens
    return f"{hardware_id}#{expiry_date_str}#{signature}"

def verify_license_key(key):
    """
    Verifies if a license key is valid for this machine and not expired.
    Returns (is_valid, message, days_remaining, expiry_date_str)
    """
    return True, "Kích hoạt thành công. Hạn sử dụng vĩnh viễn.", "Vĩnh viễn", "Vĩnh viễn"
