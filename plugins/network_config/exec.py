#!/usr/bin/env python3
import subprocess
import json

def get_network_interfaces():
    """Retrieve network interface information"""
    try:
        # Use ip command to get network interfaces
        result = subprocess.run(['ip', '-j', 'addr'], capture_output=True, text=True)
        interfaces = json.loads(result.stdout)
        return [
            {
                'name': iface.get('ifname', 'Unknown'),
                'state': iface.get('operstate', 'Unknown'),
                'address': next((addr.get('local', 'N/A') for addr in iface.get('addr_info', []) if addr.get('family') == 'inet'), 'N/A')
            }
            for iface in interfaces
        ]
    except Exception as e:
        print(f"Error retrieving network interfaces: {e}")
        return []

def configure_interface(interface_name):
    """Placeholder for interface configuration"""
    print(f"Configuring interface: {interface_name}")
    # Add actual configuration logic here

def main():
    interfaces = get_network_interfaces()
    print("Interfaces réseau disponibles:")
    for idx, iface in enumerate(interfaces, 1):
        print(f"{idx}. {iface['name']} - État: {iface['state']} - IP: {iface['address']}")

if __name__ == '__main__':
    main()
