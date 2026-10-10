#!/bin/bash
/opt/reefcore/reefchem.py pull 2>&1 | tail -1
/opt/reefcore/reefchem.py report
