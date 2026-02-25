import argparse
import time
from multirtc import dem, create_dem, geocode, multirtc
from multirtc.multimetric import ale, point_target, rle


def main():
    global_parser = argparse.ArgumentParser(
        prog='multirtc',
        description='ISCE3-based multi-sensor RTC and cal/val tool',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = global_parser.add_subparsers(title='command', help='MultiRTC sub-commands')

    rtc_parser = multirtc.create_parser(subparsers.add_parser('rtc', help=multirtc.__doc__))
    rtc_parser.set_defaults(func=multirtc.run)

    geocode_parser = multirtc.create_parser(subparsers.add_parser('geocode', help=geocode.__doc__))
    geocode_parser.set_defaults(func=geocode.run)

    dem_parser = dem.create_parser(subparsers.add_parser('prepdem', help=dem.__doc__))
    dem_parser.set_defaults(func=dem.run)

    createdem_parser = create_dem.create_parser(subparsers.add_parser('createdem', help=create_dem.__doc__))
    createdem_parser.set_defaults(func=create_dem.run)

    ale_parser = ale.create_parser(subparsers.add_parser('ale', help=ale.__doc__))
    ale_parser.set_defaults(func=ale.run)

    rle_parser = rle.create_parser(subparsers.add_parser('rle', help=rle.__doc__))
    rle_parser.set_defaults(func=rle.run)

    pt_parser = point_target.create_parser(subparsers.add_parser('pt', help=point_target.__doc__))
    pt_parser.set_defaults(func=point_target.run)

    args = global_parser.parse_args()
    start_time = time.perf_counter()
    args.func(args)
    end_time = time.perf_counter()
    elapsed_time = (end_time - start_time) / 60.0
    print(f'The code block executed in {elapsed_time:.4f} minutes')


if __name__ == '__main__':
    main()
