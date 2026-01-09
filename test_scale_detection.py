from extractor import detect_scale

test_cases = [
    ("LAPORAN POSISI KEUANGAN\n... (Dalam Jutaan Rupiah, kecuali dinyatakan lain) ...", ("Jutaan (Millions)", 1000000.0)),
    ("CONSOLIDATED STATEMENT OF FINANCIAL POSITION\n... (In Billions of Indonesian Rupiah) ...", ("Miliaran (Billions)", 1000000000.0)),
    ("LAPORAN LABA RUGI\n... (Dalam Ribuan Rupiah) ...", ("Ribuan (Thousands)", 1000.0)),
    ("STATEMENT OF PROFIT OR LOSS\n... (In Millions of Rupiah) ...", ("Jutaan (Millions)", 1000000.0)),
    ("Random text without scale info", ("Satuan Penuh (Full Units)", 1.0)),
]

def run_tests():
    passed = 0
    for text, expected in test_cases:
        result = detect_scale(text)
        if result == expected:
            print(f"PASS: Found {result[0]} for text snippet.")
            passed += 1
        else:
            print(f"FAIL: Expected {expected[0]}, got {result[0]} for text snippet.")
    
    print(f"\nSummary: {passed}/{len(test_cases)} tests passed.")

if __name__ == "__main__":
    run_tests()
