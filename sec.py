import gzip
import struct
import csv
import sys
from datetime import datetime, timedelta

class NSESecConverter:
    def __init__(self):
        # Data type sizes according to NSE specification
        self.CHAR = 1
        self.SHORT = 2
        self.LONG = 4
        
        # Header structure: Transcode(2) + Timestamp(4) + MessageLength(2) + Filler(1) = 9 bytes
        self.HEADER_FORMAT = '<HLH1s'  # Little endian format
        self.HEADER_SIZE = 9
        
        # Data structure sizes for Market Information (213 bytes)
        self.DATA_SIZE = 213
        
        # Market type mapping
        self.market_types = {
            '1': 'Normal market',
            '2': 'Odd lot market', 
            '3': 'Spot market',
            '4': 'Auction market'
        }
        
        # Security status mapping
        self.security_status = {
            '1': 'Preopen',
            '2': 'Open',
            '3': 'Suspended',
            '4': 'Preopen extended',
            '5': 'Stock Open with Market'
        }
    
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
    
    def safe_float(self, value_str):
        """Safely convert string to float"""
        try:
            clean_val = value_str.strip()
            return float(clean_val) if clean_val and clean_val != '0' else 0.0
        except:
            return 0.0
    
    def safe_int(self, value_str):
        """Safely convert string to int"""
        try:
            clean_val = value_str.strip()
            return int(clean_val) if clean_val and clean_val != '0' else 0
        except:
            return 0
    
    def parse_data_record(self, data):
        """Parse the 213-byte data record for Market Information"""
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
        
        # Market Type (CHAR[1])
        market_type_code = self.clean_string(data[offset:offset+1])
        market_type = self.market_types.get(market_type_code, market_type_code)
        offset += 1
        
        # Best Buy Price (CHAR[10])
        best_buy_price = self.clean_string(data[offset:offset+10])
        offset += 10
        
        # Best Buy Quantity (CHAR[12])
        best_buy_quantity = self.clean_string(data[offset:offset+12])
        offset += 12
        
        # Best Sell Price (CHAR[10])
        best_sell_price = self.clean_string(data[offset:offset+10])
        offset += 10
        
        # Best Sell Quantity (CHAR[12])
        best_sell_quantity = self.clean_string(data[offset:offset+12])
        offset += 12
        
        # Last Traded Price (CHAR[10])
        last_traded_price = self.clean_string(data[offset:offset+10])
        offset += 10
        
        # Total Traded Quantity (CHAR[12])
        total_traded_quantity = self.clean_string(data[offset:offset+12])
        offset += 12
        
        # Average Traded Price (CHAR[10])
        average_traded_price = self.clean_string(data[offset:offset+10])
        offset += 10
        
        # Security Status (CHAR[1])
        security_status_code = self.clean_string(data[offset:offset+1])
        security_status = self.security_status.get(security_status_code, security_status_code)
        offset += 1
        
        # Open Price (CHAR[10])
        open_price = self.clean_string(data[offset:offset+10])
        offset += 10
        
        # High Price (CHAR[10])
        high_price = self.clean_string(data[offset:offset+10])
        offset += 10
        
        # Low Price (CHAR[10])
        low_price = self.clean_string(data[offset:offset+10])
        offset += 10
        
        # Close Price (CHAR[10])
        close_price = self.clean_string(data[offset:offset+10])
        offset += 10
        
        # Interval High Price (CHAR[10])
        interval_high_price = self.clean_string(data[offset:offset+10])
        offset += 10
        
        # Interval Low Price (CHAR[10])
        interval_low_price = self.clean_string(data[offset:offset+10])
        offset += 10
        
        # Interval Open Price (CHAR[10])
        interval_open_price = self.clean_string(data[offset:offset+10])
        offset += 10
        
        # Interval Close Price (CHAR[10])
        interval_close_price = self.clean_string(data[offset:offset+10])
        offset += 10
        
        # Interval Total Traded Quantity (CHAR[12])
        interval_total_traded_quantity = self.clean_string(data[offset:offset+12])
        offset += 12
        
        return {
            'security_token': security_token,
            'instrument_name': instrument_name,
            'symbol': symbol,
            'expiry_date': expiry_date,
            'strike_price': self.safe_float(strike_price),
            'option_type': option_type,
            'market_type': market_type,
            'best_buy_price': self.safe_float(best_buy_price),
            'best_buy_quantity': self.safe_int(best_buy_quantity),
            'best_sell_price': self.safe_float(best_sell_price),
            'best_sell_quantity': self.safe_int(best_sell_quantity),
            'last_traded_price': self.safe_float(last_traded_price),
            'total_traded_quantity': self.safe_int(total_traded_quantity),
            'average_traded_price': self.safe_float(average_traded_price),
            'security_status': security_status,
            'open_price': self.safe_float(open_price),
            'high_price': self.safe_float(high_price),
            'low_price': self.safe_float(low_price),
            'close_price': self.safe_float(close_price),
            'interval_high_price': self.safe_float(interval_high_price),
            'interval_low_price': self.safe_float(interval_low_price),
            'interval_open_price': self.safe_float(interval_open_price),
            'interval_close_price': self.safe_float(interval_close_price),
            'interval_total_traded_quantity': self.safe_int(interval_total_traded_quantity)
        }
    
    def convert_to_csv(self, input_file, output_file):
        """Convert .sec.gz file to CSV"""
        records = []
        
        try:
            with gzip.open(input_file, 'rb') as f:
                record_count = 0
                while True:
                    # Read header
                    header_data = f.read(self.HEADER_SIZE)
                    if len(header_data) < self.HEADER_SIZE:
                        break
                    
                    # Parse header
                    transcode, timestamp, msg_length, filler = struct.unpack(self.HEADER_FORMAT, header_data)
                    
                    # Check if this is Market Information data (transcode = 1)
                    if transcode == 1:
                        # Read data record
                        data_record = f.read(self.DATA_SIZE)
                        if len(data_record) < self.DATA_SIZE:
                            break
                        
                        # Parse data
                        try:
                            parsed_data = self.parse_data_record(data_record)
                            
                            # Add timestamp and other header info
                            parsed_data['timestamp'] = self.parse_timestamp(timestamp)
                            parsed_data['transcode'] = transcode
                            parsed_data['message_length'] = msg_length
                            
                            records.append(parsed_data)
                            record_count += 1
                            
                            if record_count % 100 == 0:
                                print(f"Processed {record_count} records...")
                                
                        except Exception as e:
                            print(f"Error parsing record {record_count}: {e}")
                            continue
                    else:
                        # Skip non-Market Information records
                        remaining_data = msg_length - self.HEADER_SIZE
                        if remaining_data > 0:
                            f.read(remaining_data)
            
            # Write to CSV
            if records:
                with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = [
                        'timestamp', 'transcode', 'message_length',
                        'security_token', 'instrument_name', 'symbol', 
                        'expiry_date', 'strike_price', 'option_type', 'market_type',
                        'best_buy_price', 'best_buy_quantity', 
                        'best_sell_price', 'best_sell_quantity',
                        'last_traded_price', 'total_traded_quantity', 'average_traded_price',
                        'security_status', 'open_price', 'high_price', 'low_price', 'close_price',
                        'interval_high_price', 'interval_low_price', 
                        'interval_open_price', 'interval_close_price', 'interval_total_traded_quantity'
                    ]
                    
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(records)
                
                print(f"Successfully converted {len(records)} records to {output_file}")
            else:
                print("No Market Information records found in the file")
                
        except Exception as e:
            print(f"Error processing file: {e}")
            raise

def main():
   
    input_file = "258.sec.gz"
    output_file = "sec.csv"
    
    print(f"Converting {input_file} to {output_file}...")
    
    converter = NSESecConverter()
    converter.convert_to_csv(input_file, output_file)

if __name__ == "__main__":
    main()

# Example usage functions:
def convert_sec_gz_to_csv(input_file_path, output_csv_path):
    """
    Convenience function to convert NSE .sec.gz file to CSV
    
    Args:
        input_file_path (str): Path to the .sec.gz file
        output_csv_path (str): Path for the output CSV file
    """
    converter = NSESecConverter()
    converter.convert_to_csv(input_file_path, output_csv_path)
    return True

# Batch processing function
def convert_multiple_sec_files(file_list, output_dir="./"):
    """
    Convert multiple .sec.gz files to CSV
    
    Args:
        file_list (list): List of .sec.gz file paths
        output_dir (str): Output directory for CSV files
    """
    converter = NSESecConverter()
    
    for input_file in file_list:
        filename = input_file.split('/')[-1].replace('.sec.gz', '.csv')
        output_file = f"{output_dir}/{filename}"
        
        print(f"Converting {input_file}...")
        converter.convert_to_csv(input_file, output_file)
        print(f"Saved to {output_file}\n")