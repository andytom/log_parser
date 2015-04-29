import argparse
import csv
import apache_log_parser


def same_minute(a, b):
    """same_minute

       Takes two datetime objects and returns true if the occur in the same
       minute.

       :param a: A datatime object 
       :param b: A datatime object

       :returns: True if a and b both occured in the same minute and False
                 otherwise.
    """
    a_truncated = a.replace(second=0, microsecond=0)
    b_truncated = b.replace(second=0, microsecond=0)
    return a_truncated == b_truncated


def file_parser(filename):
    """file_parser

       Opens the log file, parse each line into a log entry, sort the entries
       based on the timestamp of when the server recieved the request and yield
       lists of log entires that occured in the same minute.
    
       The logformat is assumed to be "%a %l %u %t \"%r\" %>s %b %D"

       :param filename: The filename of the log file to parse.

       :returns: A list containing the parsed entries sorted by the time
                 they were received by the server.
    """
    LOG_FORMAT = "%a %l %u %t \"%r\" %>s %b %D"

    line_parser = apache_log_parser.make_parser(LOG_FORMAT)

    parsed_entries = []

    with open(filename) as f:
        for line in f:
            parsed_entries.append(line_parser(line))

    # Sort the parsed log entries by timestamp. Some of the log entries in the
    # provided example take a long time to process so they are not in order,
    # this messes up splitting the entries into minute chunks for processing.
    parsed_entries.sort(key=lambda x: x.get('time_received_utc_datetimeobj'))

    return parsed_entries


def chunk_entries(parsed_entries):
    """chunk_entries

       Takes a list of entires and yields lists of entires that were recieved
       by the server in the same minute.

       :param parsed_entries: A list of parsed log entires

       :returns: Lists of enties that were recieved by the server in the same
                 minute.
    """
    parsed_entries = iter(parsed_entries)

    run = [parsed_entries.next()]

    for entry in parsed_entries:
        if same_minute(run[-1]['time_received_utc_datetimeobj'],
                       entry['time_received_utc_datetimeobj']):
            run.append(entry)
        else:
            yield run
            run = [entry]
    yield run


def process_entries(entry_list):
    """process_entries

       Collect the information we want out of the passed list of log entries.

       :param entry_list: A list of parsed log entires.
       
       :returns: A dict containing the total number of requests, the number of
                 errors, the number of successful requests, the mean response
                 time in seconds, the total data sent in MB and the start of
                 the minuite the requests occured in.
    """
    error_count = 0
    data_sent = 0
    total_response_time = 0
    minute_start = entry_list[0]['time_received_utc_datetimeobj'].replace(second=0, microsecond=0)

    print "Processing entries starting at {}".format(minute_start)

    for entry in entry_list:
        # Treating requests with 4xx and 5xx status codes as Errors and
        # assuming that all other status codes are successful.
        if 400 <= int(entry['status']) < 600:
            error_count += 1

        # If the response is empty then we will get '-' not 0 so need to check
        # before adding it to the running data_sent total.
        if entry['response_bytes_clf'] != '-':
            data_sent += int(entry['response_bytes_clf'])
        total_response_time += int(entry['time_us'])

    success_count = len(entry_list) - error_count

    mean_respone_time = total_response_time/float(len(entry_list))

    # data is in bytes need MB
    data_sent_mb = data_sent/float(1000000)

    return {
        'error_count': error_count,
        'success_count': success_count,
        'total_requests': len(entry_list),
        'mean_respone_time': mean_respone_time,
        'data_sent_mb': data_sent_mb,
        'minute_start': minute_start,
    }


def process_file(filename):
    """process_file

       Take a log file and process it into a list of dicts containing the per
       minute stats.

       :params filename: The name of the log file to process
       :returns: A list of dicts where each dict is a processed entry
    """
    print "Reading and Parsing File: {}".format(filename)
    parsed_entries = file_parser(filename)
    print "Starting to Process Entries"
    chunked_entires = chunk_entries(parsed_entries)
    return [process_entries(entry) for entry in chunked_entires]


def write_csv(data, output_csv):
    """write_csv

       Takes a list of processed entires and writes them to a csv file.

       :params data: A list of processed entires
       :params output_csv: The name of the file where the csv data should be
                           written.
    """
    with open(output_csv, 'w') as csvfile:
        fieldnames = ['minute_start',
                      'total_requests',
                      'success_count',
                      'error_count',
                      'mean_respone_time',
                      'data_sent_mb']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for row in data:
            row['minute_start'] = row['minute_start'].isoformat()
            writer.writerow(row)


def calculate_averages(data):
    """calculate_averages

       Take a list of dicts and calculate then print the averages for the
       list.

       :param data: A list of dicts contain the keys 'error_count',
                    'success_count', 'mean_respone_time' and 'data_sent_mb'.

       :returns: A dict containing the mean error_count, success_count,
                 mean_respone_time and data_sent_mb.
    """
    def mean(item_key):
        all_items = [i[item_key] for i in data]
        return sum(all_items)/float(len(all_items))

    return {
        "mean_error_count": mean('error_count'),
        "mean_success_count": mean('success_count'),
        "mean_mean_response_time": mean('mean_respone_time'),
        "mean_data_sent_mb": mean('data_sent_mb'),
    }


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description="""Process an Apache logfile in format
            '%a %l %u %t \"%r\" %>s %b %D' and calculate the: No. of successful
            requests per minute, No. of error requests per minute, Mean
            response time per minute and MBs sent per minute. Optionally can
            output the data broken down by minute to a csv for further
            processing.""")

    parser.add_argument("log_file", help="Log file to Process")
    parser.add_argument("-o", "--output_csv",
                        help="Write the processed data to OUTPUT_CSV.")
    args = parser.parse_args()

    data = process_file(args.log_file)

    if args.output_csv:
        print "Writing to {}".format(args.output_csv)
        write_csv(data, args.output_csv)

    averages = calculate_averages(data)
    print "-" * 80
    print "Mean errors per min: {}".format(averages['mean_error_count'])
    print "Mean successful requests per min: {}".format(averages['mean_success_count'])
    print "Mean response time in microseconds per min: {}".format(averages['mean_mean_response_time'])
    print "Mean MBs sent per min: {}".format(averages['mean_data_sent_mb'])
    print "-" * 80
