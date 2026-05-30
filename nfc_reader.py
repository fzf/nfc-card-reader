#!/usr/bin/env python3
"""
NFC Card Reader for ACR1252
Continuously polls for NFC cards and displays their UID and data
"""

from smartcard.System import readers
from smartcard.util import toHexString
import time
import sys

def read_memory_dump(connection):
    """Attempt to dump memory contents from MIFARE Ultralight/NTAG cards"""
    memory_data = []

    # Try to read pages 0-255 (most cards have far fewer, but we'll try)
    # MIFARE Ultralight has ~16-64 pages, NTAG has up to 231 pages
    print(f"\n{'='*60}", flush=True)
    print("MEMORY DUMP:", flush=True)
    print(f"{'='*60}", flush=True)

    for page in range(0, 256):
        try:
            # READ BINARY command for MIFARE Ultralight/NTAG
            # Format: [0xFF, 0xB0, 0x00, page, length]
            READ_PAGE = [0xFF, 0xB0, 0x00, page, 0x04]  # Read 4 bytes per page

            data, sw1, sw2 = connection.transmit(READ_PAGE)

            if sw1 == 0x90 and sw2 == 0x00:
                hex_data = ' '.join(f'{b:02X}' for b in data)
                ascii_data = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
                print(f"Page {page:3d}: {hex_data:11s}  |  {ascii_data}", flush=True)
                memory_data.append({
                    'page': page,
                    'data': data,
                    'hex': hex_data
                })
            else:
                # End of memory or error
                break

        except Exception as e:
            # End of readable memory
            break

    print(f"{'='*60}", flush=True)
    print(f"Total pages read: {len(memory_data)}", flush=True)
    print(f"{'='*60}\n", flush=True)

    return memory_data

def read_nfc_card(reader):
    """Read NFC card UID and data from a specific reader"""
    try:
        # Try to connect to the reader (requires card present)
        connection = reader.createConnection()
        connection.connect()

        # Get ATR (Answer To Reset)
        atr = connection.getATR()
        print(f"\n{'='*60}", flush=True)
        print(f"ATR: {toHexString(atr)}", flush=True)

        # Read UID using GET_UID command (for ISO14443A cards)
        GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]

        try:
            data, sw1, sw2 = connection.transmit(GET_UID)

            if sw1 == 0x90 and sw2 == 0x00:
                uid = toHexString(data)
                uid_decimal = int(uid.replace(' ', ''), 16)

                print(f"UID (Hex):     {uid}", flush=True)
                print(f"UID (Decimal): {uid_decimal}", flush=True)
                print(f"UID (Bytes):   {' '.join(f'{b:02X}' for b in data)}", flush=True)
                print(f"UID Length:    {len(data)} bytes", flush=True)
                print(f"Status:        Card detected", flush=True)
                print(f"{'='*60}\n", flush=True)

                # Dump memory contents
                memory_data = read_memory_dump(connection)

                return {
                    'uid_hex': uid,
                    'uid_decimal': uid_decimal,
                    'uid_bytes': data,
                    'atr': toHexString(atr),
                    'memory': memory_data
                }
            else:
                print(f"Error reading UID: SW1={sw1:02X} SW2={sw2:02X}")
                return None

        except Exception as e:
            print(f"Error communicating with card: {e}")
            return None
        finally:
            connection.disconnect()

    except Exception as e:
        # No card present or connection error - silently return None
        return None

def main():
    """Main loop - continuously poll for cards"""
    print("NFC Card Reader - ACR1252")
    print("Press Ctrl+C to exit\n")

    # Find the ACR1252 reader once at startup
    reader_list = readers()
    if not reader_list:
        print("ERROR: No card readers found!")
        sys.exit(1)

    acr_reader = None
    for reader in reader_list:
        # Use PICC interface for NFC cards (not SAM)
        if 'ACR1252' in str(reader) and 'PICC' in str(reader):
            acr_reader = reader
            break

    if not acr_reader:
        print("ERROR: ACR1252 reader not found!")
        print("Available readers:", reader_list)
        sys.exit(1)

    print(f"Using reader: {acr_reader}")
    print("Waiting for card tap...\n")

    last_uid = None
    card_present = False

    while True:
        try:
            result = read_nfc_card(acr_reader)

            if result:
                current_uid = result['uid_hex']

                # Only update state on new card detection
                if not card_present or current_uid != last_uid:
                    last_uid = current_uid
                    card_present = True

            else:
                # Card was removed
                if card_present:
                    print("Card removed. Waiting for next tap...\n")
                    last_uid = None
                    card_present = False

            # Poll every 0.3 seconds
            time.sleep(0.3)

        except KeyboardInterrupt:
            print("\n\nExiting...")
            sys.exit(0)
        except Exception as e:
            # Reader might not be ready or card removed
            if card_present:
                card_present = False
                last_uid = None
            time.sleep(0.3)

if __name__ == "__main__":
    main()
