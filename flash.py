"""Build and upload with PlatformIO; the serial port must be explicitly selected."""
import argparse
from pathlib import Path
import subprocess
import sys

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',required=True)
    parser.add_argument('--build',choices=['display','headless'],default='display')
    args=parser.parse_args()
    subprocess.run([sys.executable,'-m','platformio','run','--project-dir',str(Path(__file__).parent/'firmware'),
                    '-e',args.build,'-t','upload','--upload-port',args.port],check=True)

if __name__=='__main__':main()
