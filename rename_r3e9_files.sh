#!/bin/bash

set -e

echo "=============================================="
echo " R3E.9 FILE RENAME"
echo "=============================================="

rename_file() {
    OLD="$1"
    NEW="$2"

    if [ -f "$OLD" ]; then
        mv "$OLD" "$NEW"
        echo "RENAMED: $OLD -> $NEW"
    elif [ -f "$NEW" ]; then
        echo "ALREADY OK: $NEW"
    else
        echo "ERROR: Neither $OLD nor $NEW exists."
        exit 1
    fi
}

rename_file "riskgovernor_r3e9.py" \
            "riskgovernor.py"

rename_file "portfoliooptimizer_r3e9.py" \
            "portfoliooptimizer.py"

rename_file "portfoliodecisionengine_r3e9.py" \
            "portfoliodecisionengine.py"

rename_file "test_riskgovernor_r3e9.py" \
            "test_riskgovernor.py"

rename_file "test_portfoliooptimizer_r3e9.py" \
            "test_portfoliooptimizer.py"

rename_file "test_portfoliodecisionengine_r3e9.py" \
            "test_portfoliodecisionengine.py"

echo ""
echo "=============================================="
echo " R3E.9 RENAME COMPLETE"
echo "=============================================="

echo ""
echo "Canonical files now present:"
echo ""

for FILE in \
    riskgovernor.py \
    portfoliooptimizer.py \
    portfoliodecisionengine.py \
    test_riskgovernor.py \
    test_portfoliooptimizer.py \
    test_portfoliodecisionengine.py
do
    if [ -f "$FILE" ]; then
        echo "  ✓ $FILE"
    else
        echo "  ✗ MISSING: $FILE"
    fi
done

echo ""
echo "Done."
