#!/usr/bin/env python3
"""
Script to write a URL to an NFC tag using pyscard (PCSC).
This will write the URL in NDEF format so it can be read by smartphones.
Supports continuous operation - keeps running and writes to each new card detected.
"""

from smartcard.System import readers
from smartcard.util import toHexString, toBytes
from smartcard.CardMonitoring import CardMonitor, CardObserver
from smartcard.Exceptions import NoCardException
import sys
import time

def create_ndef_url_message(url):
    """
    Create an NDEF message containing a URL record.
    Returns the raw bytes to write to the NFC tag.
    """
    # NDEF URL Record format
    # Bit 7: MB (Message Begin) = 1
    # Bit 6: ME (Message End) = 1
    # Bit 5: CF (Chunk Flag) = 0
    # Bit 4: SR (Short Record) = 1
    # Bit 3: IL (ID Length) = 0
    # Bits 2-0: TNF (Type Name Format) = 001 (Well Known)
    tnf = 0xD1  # MB=1, ME=1, CF=0, SR=1, IL=0, TNF=001

    # Type Length = 1 (for 'U')
    type_length = 0x01

    # Calculate payload length
    # URL identifier code (1 byte) + URL without protocol
    url_prefix_codes = {
        'http://www.': 0x01,
        'https://www.': 0x02,
        'http://': 0x03,
        'https://': 0x04,
    }

    # Find the appropriate prefix
    url_code = 0x00  # No prefix
    url_without_prefix = url

    for prefix, code in url_prefix_codes.items():
        if url.startswith(prefix):
            url_code = code
            url_without_prefix = url[len(prefix):]
            break

    # Encode the URL part
    url_bytes = url_without_prefix.encode('utf-8')
    payload_length = 1 + len(url_bytes)  # 1 byte for URL code + URL string

    # Type = 'U' (URI)
    record_type = ord('U')

    # Build the NDEF message
    ndef_message = [
        tnf,
        type_length,
        payload_length,
        record_type,
        url_code
    ] + list(url_bytes)

    # NDEF message wrapper (TLV format)
    # TLV: Type (0x03 = NDEF Message), Length, Value
    tlv_type = 0x03
    tlv_length = len(ndef_message)
    tlv_terminator = 0xFE

    full_message = [tlv_type, tlv_length] + ndef_message + [tlv_terminator]

    return full_message

def write_to_ntag(connection, url):
    """Write URL to an NTAG (NTAG213/215/216) NFC tag."""

    print(f"Creating NDEF message for: {url}")
    ndef_data = create_ndef_url_message(url)

    print(f"NDEF message: {toHexString(ndef_data)}")
    print(f"Message length: {len(ndef_data)} bytes")

    # NTAG uses page-based writing (4 bytes per page)
    # User memory starts at page 4
    # Pages 0-3: UID and manufacturer data (read-only)
    # Page 4+: User data

    start_page = 4

    # Pad the data to a multiple of 4 bytes
    while len(ndef_data) % 4 != 0:
        ndef_data.append(0x00)

    # Write data in 4-byte chunks (pages)
    for i in range(0, len(ndef_data), 4):
        page = start_page + (i // 4)
        data_chunk = ndef_data[i:i+4]

        # WRITE command: 0xA2 (compatibility write)
        apdu = [0xFF, 0xD6, 0x00, page, 0x04] + data_chunk

        print(f"Writing page {page}: {toHexString(data_chunk)}")

        response, sw1, sw2 = connection.transmit(apdu)

        if sw1 == 0x90 and sw2 == 0x00:
            print(f"  ✓ Page {page} written successfully")
        else:
            print(f"  ✗ Error writing page {page}: SW={sw1:02X} {sw2:02X}")
            return False

    print("\n✓ Successfully wrote URL to NFC tag!")
    return True

def process_card(reader, url):
    """Process a single card - connect, write, and disconnect."""
    try:
        # Create connection
        connection = reader.createConnection()
        connection.connect()

        print("✓ Tag detected!")

        # Get ATR (Answer To Reset)
        atr = connection.getATR()
        print(f"ATR: {toHexString(atr)}")

        # Get UID
        get_uid = [0xFF, 0xCA, 0x00, 0x00, 0x00]
        response, sw1, sw2 = connection.transmit(get_uid)

        if sw1 == 0x90 and sw2 == 0x00:
            print(f"UID: {toHexString(response)}")

        # Write the URL
        success = write_to_ntag(connection, url)

        if success:
            print("\n" + "=" * 50)
            print("Tag is ready! You can now tap it with your phone.")
            print("=" * 50)
            return True
        else:
            print("\n✗ Failed to write URL to tag")
            return False

    except NoCardException:
        # Card was removed, this is normal
        return False
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False

class NFCCardObserver(CardObserver):
    """Observer that monitors for card insertions."""

    def __init__(self, reader, url):
        self.reader = reader
        self.url = url
        self.processing = False

    def update(self, observable, actions):
        """Called when a card event occurs."""
        (addedcards, removedcards) = actions

        for card in addedcards:
            if not self.processing:
                self.processing = True
                print("\n" + "=" * 50)
                print(f"Card detected on {card.reader}")
                print("=" * 50)
                process_card(self.reader, self.url)
                print("\nWaiting for next card... (Press Ctrl+C to exit)")
                print("-" * 50)
                self.processing = False

        for card in removedcards:
            pass  # Card removed, ignore

def main():
    url = "http://cardy-mc-cardface.tacodogs.org"

    print("NFC Tag Writer - Continuous Mode")
    print("=" * 50)
    print(f"URL to write: {url}")
    print("This script will keep running and write to each card you place on the reader.")
    print("Press Ctrl+C to exit.\n")

    # Get available readers
    available_readers = readers()

    if not available_readers:
        print("✗ No smart card readers found!")
        print("Please make sure your NFC reader is connected.")
        return 1

    print("Available readers:")
    for idx, reader in enumerate(available_readers):
        print(f"  {idx}: {reader}")

    # Use the PICC (Proximity Integrated Circuit Card) reader
    target_reader = None
    for reader in available_readers:
        if "PICC" in str(reader):
            target_reader = reader
            break

    if not target_reader:
        target_reader = available_readers[0]

    print(f"\nUsing reader: {target_reader}")
    print("\nWaiting for card... (Press Ctrl+C to exit)")
    print("-" * 50)

    # Set up card monitoring
    cardmonitor = CardMonitor()
    cardobserver = NFCCardObserver(target_reader, url)
    cardmonitor.addObserver(cardobserver)

    try:
        # Keep running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nExiting...")
        cardmonitor.deleteObserver(cardobserver)
        return 0

if __name__ == "__main__":
    sys.exit(main())
