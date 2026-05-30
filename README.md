# NFC Card Reader

Python scripts for reading and writing NFC cards and EMV credit/debit cards using the ACR1252 reader.

## Features

- **nfc_reader.py** - Read basic NFC cards (MIFARE, NTAG, etc.)
  - Displays card UID
  - Dumps complete memory contents
  - Real-time card detection

- **emv_reader.py** - Read EMV credit/debit cards
  - Extracts card number (PAN)
  - Reads expiration date
  - Displays cardholder name (if available)
  - Shows application information

- **write_nfc_url_pcsc.py** - Write URLs to NFC tags
  - Creates NDEF-formatted URL records
  - Continuous operation mode
  - Compatible with NTAG213/215/216 tags
  - URLs readable by smartphones

## Requirements

- ACR1252 Dual Reader (PICC interface)
- Python 3.x
- pyscard library

## Installation

```bash
pip install pyscard
```

## Usage

### Reading NFC Cards
```bash
python3 nfc_reader.py
```

### Reading EMV Cards
```bash
python3 emv_reader.py
```

**Important**: When reading credit cards, hold the card steady on the reader for 3-5 seconds.

### Writing URLs to NFC Tags
```bash
python3 write_nfc_url_pcsc.py
```

Edit the `url` variable in the script to customize the URL. The script will continuously wait for tags and write to each one detected.

## Security Notes

- EMV cards do **NOT** expose CVV/PIN data
- Only publicly readable data is extracted
- Cannot be used to clone cards due to dynamic cryptograms
- For educational and research purposes only

## License

MIT
