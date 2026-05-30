#!/usr/bin/env python3
"""
EMV Credit/Debit Card Reader for ACR1252
Reads publicly available information from EMV cards
"""

from smartcard.System import readers
from smartcard.util import toHexString, toBytes
import time
import sys

def parse_tlv(data, depth=0):
    """Parse TLV (Tag-Length-Value) encoded data recursively"""
    result = {}
    i = 0
    while i < len(data):
        if i >= len(data):
            break

        # Read tag
        tag = data[i]
        i += 1

        # Handle multi-byte tags (when low 5 bits are all 1s)
        if (tag & 0x1F) == 0x1F and i < len(data):
            tag = (tag << 8) | data[i]
            i += 1
            # Handle 3-byte tags if needed
            while i < len(data) and (data[i-1] & 0x80):
                tag = (tag << 8) | data[i]
                i += 1

        if i >= len(data):
            break

        # Read length
        length = data[i]
        i += 1

        # Handle multi-byte length
        if length & 0x80:
            num_bytes = length & 0x7F
            length = 0
            for _ in range(num_bytes):
                if i >= len(data):
                    break
                length = (length << 8) | data[i]
                i += 1

        # Read value
        if i + length <= len(data):
            value = data[i:i+length]
            result[tag] = value

            # Recursively parse constructed tags
            # Check if it's a constructed tag (bit 6 set in first byte of tag)
            first_tag_byte = tag if tag <= 0xFF else (tag >> 8)
            is_constructed = (first_tag_byte & 0x20) != 0

            if is_constructed:
                nested = parse_tlv(value, depth + 1)
                result.update(nested)

            i += length
        else:
            break

    return result

def read_emv_card(reader):
    """Read EMV card data"""
    connection = None
    try:
        connection = reader.createConnection()

        # Try different protocols - T=1 is common for EMV
        try:
            from smartcard.scard import SCARD_PROTOCOL_T1, SCARD_PROTOCOL_T0
            connection.connect(protocol=SCARD_PROTOCOL_T1)
        except:
            try:
                connection.connect(protocol=SCARD_PROTOCOL_T0)
            except:
                connection.connect()

        print(f"\n{'='*70}", flush=True)
        print("EMV CARD DETECTED - KEEP CARD ON READER!", flush=True)
        print(f"{'='*70}", flush=True)

        # Get ATR
        atr = connection.getATR()
        print(f"ATR: {toHexString(atr)}", flush=True)

        # Small delay to ensure card is ready
        time.sleep(0.1)

        # SELECT PPSE (Proximity Payment System Environment)
        SELECT_PPSE = [0x00, 0xA4, 0x04, 0x00, 0x0E,
                       0x32, 0x50, 0x41, 0x59, 0x2E, 0x53, 0x59, 0x53,
                       0x2E, 0x44, 0x44, 0x46, 0x30, 0x31, 0x00]

        print("\nSending SELECT PPSE command...", flush=True)
        data, sw1, sw2 = connection.transmit(SELECT_PPSE)

        if sw1 == 0x90 and sw2 == 0x00:
            print(f"Response: {toHexString(data)}", flush=True)
            print(f"Status: {sw1:02X} {sw2:02X} (Success)", flush=True)

            # Parse response
            parsed = parse_tlv(data)

            print(f"\nParsed tags found:", flush=True)
            for tag, value in parsed.items():
                print(f"  Tag 0x{tag:02X}: {toHexString(value)}", flush=True)

            # Try to find AID (Application ID)
            # Tag 0x4F is AID, Tag 0x50 is Application Label
            for tag, value in parsed.items():
                if tag == 0x4F:
                    print(f"\nApplication ID (AID): {toHexString(value)}", flush=True)
                elif tag == 0x50:
                    app_label = ''.join(chr(b) if 32 <= b < 127 else '.' for b in value)
                    print(f"Application Label: {app_label}", flush=True)

            # Try to SELECT the first AID found
            if 0x4F in parsed:
                aid = parsed[0x4F]
                print(f"\nSelecting application...", flush=True)

                SELECT_AID = [0x00, 0xA4, 0x04, 0x00, len(aid)] + list(aid) + [0x00]
                data, sw1, sw2 = connection.transmit(SELECT_AID)

                if sw1 == 0x90 and sw2 == 0x00:
                    print(f"Application selected successfully", flush=True)
                    print(f"Response: {toHexString(data)}", flush=True)

                    # Try to read records directly (some cards allow this without GPO)
                    print(f"\nReading card records...", flush=True)
                    records_found = 0
                    for sfi in range(1, 32):  # Try different Short File Identifiers
                        sfi_has_records = False
                        for record in range(1, 17):  # Try different record numbers
                            READ_RECORD = [0x00, 0xB2, record, (sfi << 3) | 0x04, 0x00]
                            try:
                                data, sw1, sw2 = connection.transmit(READ_RECORD)
                                if sw1 == 0x90 and sw2 == 0x00 and len(data) > 0:
                                    records_found += 1
                                    sfi_has_records = True
                                    print(f"\n--- SFI {sfi}, Record {record} ---", flush=True)
                                    print(f"Raw: {toHexString(data)}", flush=True)

                                    # Parse for interesting tags
                                    parsed_rec = parse_tlv(data)

                                    # Tag 0x57 = Track 2 Equivalent Data (contains PAN)
                                    if 0x57 in parsed_rec:
                                        track2 = toHexString(parsed_rec[0x57])
                                        print(f"Track 2 Data: {track2}", flush=True)
                                        # Extract PAN (card number) - before 'D' separator
                                        if 'D' in track2:
                                            parts = track2.split('D')
                                            pan = parts[0].replace(' ', '')
                                            after_d = parts[1].replace(' ', '')
                                            print(f"DEBUG: After D separator: '{after_d}'", flush=True)

                                            # Format is YYMM (4 digits)
                                            if len(after_d) >= 4:
                                                year = after_d[0:2]
                                                month = after_d[2:4]
                                                print(f"💳 Card Number: {pan}", flush=True)
                                                print(f"📅 Expiration: {month}/20{year}", flush=True)

                                    # Tag 0x5A = PAN (Primary Account Number)
                                    if 0x5A in parsed_rec:
                                        pan_bytes = parsed_rec[0x5A]
                                        pan = ''.join(f'{b:02X}' for b in pan_bytes)
                                        print(f"💳 PAN: {pan}", flush=True)

                                    # Tag 0x5F24 = Expiration Date
                                    if 0x5F24 in parsed_rec:
                                        exp_date = toHexString(parsed_rec[0x5F24]).replace(' ', '')
                                        print(f"📅 Expiration Date: 20{exp_date[0:2]}-{exp_date[2:4]}", flush=True)

                                    # Tag 0x5F20 = Cardholder Name
                                    if 0x5F20 in parsed_rec:
                                        name = ''.join(chr(b) if 32 <= b < 127 else '' for b in parsed_rec[0x5F20])
                                        print(f"👤 Cardholder: {name.strip()}", flush=True)

                                    # Tag 0x9F42 = Currency Code
                                    if 0x9F42 in parsed_rec:
                                        currency = toHexString(parsed_rec[0x9F42])
                                        print(f"💵 Currency: {currency}", flush=True)

                                    # Tag 0x5F34 = PAN Sequence Number
                                    if 0x5F34 in parsed_rec:
                                        seq = parsed_rec[0x5F34][0]
                                        print(f"🔢 PAN Sequence: {seq}", flush=True)

                                elif sw1 == 0x6A and sw2 == 0x83:
                                    # Record not found - stop trying this SFI
                                    break
                                elif sw1 == 0x69 and sw2 == 0x85:
                                    # Conditions not satisfied - try next
                                    break
                            except Exception as e:
                                break

                        # If we found records in this SFI, continue searching other SFIs
                        # Otherwise, if we've checked a few SFIs with no results, we can stop
                        if not sfi_has_records and sfi > 5:
                            break

                    if records_found == 0:
                        print("No publicly readable records found.", flush=True)
                        print("This card may require authentication or have restricted access.", flush=True)
                else:
                    print(f"Failed to select application: {sw1:02X} {sw2:02X}", flush=True)

        else:
            print(f"PPSE selection failed: {sw1:02X} {sw2:02X}", flush=True)
            print("This might not be an EMV contactless card", flush=True)

        print(f"{'='*70}\n", flush=True)

        if connection:
            try:
                connection.disconnect()
            except:
                pass
        return True

    except Exception as e:
        # Silently handle "no card" errors, print others
        error_msg = str(e)
        if "No smart card inserted" not in error_msg:
            print(f"Error: {e}", flush=True)
        if connection:
            try:
                connection.disconnect()
            except:
                pass
        return False

def main():
    """Main loop - continuously poll for cards"""
    print("EMV Card Reader - ACR1252")
    print("Press Ctrl+C to exit\n")

    # Find the ACR1252 PICC reader
    reader_list = readers()
    if not reader_list:
        print("ERROR: No card readers found!")
        sys.exit(1)

    acr_reader = None
    for reader in reader_list:
        if 'ACR1252' in str(reader) and 'PICC' in str(reader):
            acr_reader = reader
            break

    if not acr_reader:
        print("ERROR: ACR1252 PICC reader not found!")
        print("Available readers:", reader_list)
        sys.exit(1)

    print(f"Using reader: {acr_reader}")
    print("Waiting for card tap...\n")

    card_present = False

    while True:
        try:
            result = read_emv_card(acr_reader)

            if result:
                card_present = True
            else:
                if card_present:
                    print("Card removed. Waiting for next tap...\n")
                    card_present = False

            time.sleep(1)  # Poll every second

        except KeyboardInterrupt:
            print("\n\nExiting...")
            sys.exit(0)
        except Exception as e:
            if card_present:
                card_present = False
            time.sleep(1)

if __name__ == "__main__":
    main()
