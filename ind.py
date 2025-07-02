import gzip
import struct
import csv
import sys
from datetime import datetime, timedelta

class NSEIndConverter:
    def __init__(self):
        # Data type sizes according to NSE specification
        self.CHAR = 1
        self.SHORT = 2
        self.LONG = 4
        
        # Header structure: Transcode(2) + Timestamp(4) + MessageLength(2) + Filler(1) = 9 bytes
        self.HEADER_FORMAT = '<HLH1s'  # Little endian format
        self.HEADER_SIZE = 9
        
        # Data structure sizes for Open Interest (54 bytes)
        self.DATA_SIZE = 54
        
    def parse_timestamp(self, timestamp):
        """Convert NSE timestamp to readable format"""
        # NSE timestamp is seconds since Jan 1, 1980
        base_date = datetime(1980, 1, 1)
        return base_date + timedelta(seconds=timestamp)
    
    def clean_string(self, byte_data):
        """Clean and decode byte data to string"""
        try:
            return byte_data.decode('ascii').strip('\x00').strip()
        except:
            return byte_data.strip(b'\x00').decode('ascii', errors='ignore').strip()
    
    def parse_data_record(self, data):
        """Parse the 54-byte data record for Open Interest"""
        offset = 0
        
        # Security Token (LONG - 4 bytes)
        security_token = struct.unpack('<L', data[offset:offset+4])[0]
        offset += 4
        
        # Instrument Name (CHAR[6])
        instrument_name = self.clean_string(data[offset:offset+6])
        offset += 6
        
        # Symbol (CHAR[10])
        symbol = self.clean_string(data[offset:offset+10])
        offset += 10
        
        # Expiry Date (CHAR[11])
        expiry_date = self.clean_string(data[offset:offset+11])
        offset += 11
        
        # Strike Price (CHAR[10])
        strike_price = self.clean_string(data[offset:offset+10])
        offset += 10
        
        # Option Type (CHAR[2])
        option_type = self.clean_string(data[offset:offset+2])
        offset += 2
        
        # Open Interest (CHAR[10])
        open_interest = self.clean_string(data[offset:offset+10])
        offset += 10
        
        # Market Type (CHAR[1])
        market_type = self.clean_string(data[offset:offset+1])
        
        return {
            'security_token': security_token,
            'instrument_name': instrument_name,
            'symbol': symbol,
            'expiry_date': expiry_date,
            'strike_price': strike_price,
            'option_type': option_type,
            'open_interest': open_interest,
            'market_type': market_type
        }
    
    def convert_to_csv(self, input_file, output_file):
        """Convert .ind.gz file to CSV"""
        records = []
        
        try:
            with gzip.open(input_file, 'rb') as f:
                while True:
                    # Read header
                    header_data = f.read(self.HEADER_SIZE)
                    if len(header_data) < self.HEADER_SIZE:
                        break
                    
                    # Parse header
                    transcode, timestamp, msg_length, filler = struct.unpack(self.HEADER_FORMAT, header_data)
                    
                    # Check if this is Open Interest data (transcode = 2)
                    if transcode == 2:
                        # Read data record
                        data_record = f.read(self.DATA_SIZE)
                        if len(data_record) < self.DATA_SIZE:
                            break
                        
                        # Parse data
                        parsed_data = self.parse_data_record(data_record)
                        
                        # Add timestamp and other header info
                        parsed_data['timestamp'] = self.parse_timestamp(timestamp)
                        parsed_data['transcode'] = transcode
                        parsed_data['message_length'] = msg_length
                        
                        records.append(parsed_data)
                    else:
                        # Skip non-Open Interest records
                        remaining_data = msg_length - self.HEADER_SIZE
                        if remaining_data > 0:
                            f.read(remaining_data)
            
            # Write to CSV
            if records:
                with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = [
                        'timestamp', 'transcode', 'message_length',
                        'security_token', 'instrument_name', 'symbol', 
                        'expiry_date', 'strike_price', 'option_type', 
                        'open_interest', 'market_type'
                    ]
                    
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(records)
                
                print(f"Successfully converted {len(records)} records to {output_file}")
            else:
                print("No Open Interest records found in the file")
                
        except Exception as e:
            print(f"Error processing file: {e}")
            raise

def main():
   
    input_file = "258.ind.gz"
    output_file = "index.csv"
    
    converter = NSEIndConverter()
    converter.convert_to_csv(input_file, output_file)

if __name__ == "__main__":
    main()
