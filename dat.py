import struct
import csv

# --- adjust this to point at your Securities.dat ---
INPUT_FILE  = 'Securities.dat'
OUTPUT_FILE = 'Securities.csv'

# Each record is: 8-byte header + 124-byte data = 132 bytes
HEADER_FMT = '<H I H'               # Transcode (ushort), Timestamp (uint), MessageLength (ushort)
DATA_FMT   = '<' + \
             'I'   +  '6s' + '10s' + '2s' + '2s' + \
             'I'*6 +  '25s' + 'I'*6 +  '25s' + 'c' + 'c'
# breakdown:
#   I              Token Number
#   6s             Instrument Name
#   10s            Symbol
#   2s             Series
#   2s             Option Type
#   I x 6          ExpiryDate, StrikePrice, IssueStartDate,
#                  MaturityDate, BoardLotQuantity, TickSize
#   25s            Security Name
#   I x 6          RecordDate, ExDate,
#                  NoDeliveryStartDate, NoDeliveryEndDate,
#                  BookClosureStartDate, BookClosureEndDate
#   25s            Remarks
#   c              Category
#   c              Filler

RECORD_SIZE = struct.calcsize(HEADER_FMT) + struct.calcsize(DATA_FMT)

# friendly names for CSV header
FIELD_NAMES = [
    'Transcode', 'Timestamp', 'MessageLength',
    'TokenNumber', 'InstrumentName', 'Symbol',
    'Series', 'OptionType', 'ExpiryDate',
    'StrikePrice', 'IssueStartDate', 'MaturityDate',
    'BoardLotQuantity', 'TickSize', 'SecurityName',
    'RecordDate', 'ExDate', 'NoDeliveryStartDate',
    'NoDeliveryEndDate', 'BookClosureStartDate',
    'BookClosureEndDate', 'Remarks', 'Category'
]

def parse_record(chunk):
    # split header / data
    hdr = chunk[:struct.calcsize(HEADER_FMT)]
    dat = chunk[struct.calcsize(HEADER_FMT):]

    transcode, timestamp, msglen = struct.unpack(HEADER_FMT, hdr)
    unpacked = struct.unpack(DATA_FMT, dat)

    # decode text fields and strip padding
    # fields: unpacked[0] = TokenNumber
    row = {
        'Transcode':       transcode,
        'Timestamp':       timestamp,
        'MessageLength':   msglen,
        'TokenNumber':     unpacked[0],
        'InstrumentName':  unpacked[1].decode('ascii', 'ignore').strip(),
        'Symbol':          unpacked[2].decode('ascii', 'ignore').strip(),
        'Series':          unpacked[3].decode('ascii', 'ignore').strip(),
        'OptionType':      unpacked[4].decode('ascii', 'ignore').strip(),
        'ExpiryDate':      unpacked[5],
        'StrikePrice':     unpacked[6],
        'IssueStartDate':  unpacked[7],
        'MaturityDate':    unpacked[8],
        'BoardLotQuantity':unpacked[9],
        'TickSize':        unpacked[10],
        'SecurityName':    unpacked[11].decode('ascii', 'ignore').strip(),
        'RecordDate':      unpacked[12],
        'ExDate':          unpacked[13],
        'NoDeliveryStartDate':unpacked[14],
        'NoDeliveryEndDate':  unpacked[15],
        'BookClosureStartDate':unpacked[16],
        'BookClosureEndDate':  unpacked[17],
        'Remarks':         unpacked[18].decode('ascii', 'ignore').strip(),
        'Category':        unpacked[19].decode('ascii', 'ignore')
    }
    return row

with open(INPUT_FILE, 'rb') as f, open(OUTPUT_FILE, 'w', newline='') as csvf:
    writer = csv.DictWriter(csvf, fieldnames=FIELD_NAMES)
    writer.writeheader()

    while True:
        chunk = f.read(RECORD_SIZE)
        if len(chunk) < RECORD_SIZE:
            break
        row = parse_record(chunk)
        writer.writerow(row)

print(f"Wrote {OUTPUT_FILE} ({RECORD_SIZE}-byte records)") 
