import os
import argparse
import json
from extractor import extract_text_from_pdf, filter_relevant_pages, analyze_page_with_llm, merge_financials
from schemas import ExtractedFinancials

def main():
    parser = argparse.ArgumentParser(description="Extract financial data from PDF.")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    args = parser.parse_args()
    
    pdf_path = args.pdf_path
    
    print(f"Processing: {pdf_path}")
    
    # 1. Extract Text
    print("Extracting text from PDF...")
    pages_text = extract_text_from_pdf(pdf_path)
    if not pages_text:
        print("Failed to extract text.")
        return

    # 2. Filter Relevant Pages
    print("Filtering relevant pages...")
    relevant_map = filter_relevant_pages(pages_text)
    print(f"Relevant Pages Map: {relevant_map}")
    
    # Collect indices
    indices_to_process = set(relevant_map['balance_sheet'] + relevant_map['income_statement'])
    
    if not indices_to_process:
        print("No relevant pages found by heuristics. Trying to process first 5 pages as fallback...")
        indices_to_process = set(range(min(5, len(pages_text))))
    
    extracted_results = []
    
    # 3. Analyze with LLM
    print(f"Analyzing {len(indices_to_process)} pages with LLM...")
    for i in indices_to_process:
        print(f" -> Analyzing Page {i+1}...")
        text = pages_text[i]
        try:
            result = analyze_page_with_llm(text)
            if result:
                extracted_results.append(result)
                # print(f"    Extracted: {result.company_name} - {result.report_period}")
        except Exception as e:
            print(f"    Failed to analyze page {i+1}: {e}")
            
    # 4. Merge Results
    print("Merging results...")
    final_data = merge_financials(extracted_results)
    
    if final_data:
        # Save to JSON
        output_file = "extracted_data.json"
        with open(output_file, "w") as f:
            f.write(final_data.model_dump_json(indent=2))
        print(f"Success! Data saved to {output_file}")
        
        # Print Summary
        print("\n--- Extraction Summary ---")
        print(f"Company: {final_data.company_name}")
        print(f"Period: {final_data.report_period}")
        print(f"Total Assets: {final_data.balance_sheet.total_assets.value if final_data.balance_sheet.total_assets else 'N/A'}")
        print(f"Net Income: {final_data.income_statement.net_income.value if final_data.income_statement.net_income else 'N/A'}")
        
    else:
        print("Failed to extract any structured data.")

if __name__ == "__main__":
    main()
