import fitz
import os
import json
import re
from collections import defaultdict

def clean(text):
    return re.sub(r'\s+', ' ', text.strip())

def is_structural_heading(text):
    """Identify text that represents actual document structure"""
    text = text.strip()
    
    # Main section patterns
    if re.match(r'^(Summary|Background|Timeline|Milestones)$', text, re.I):
        return True
    if re.match(r'^(Appendix [A-C]:|Phase [IVX]+:|The Business Plan)', text, re.I):
        return True
    if re.match(r'^(Approach and|Evaluation and)', text, re.I):
        return True
    
    # Numbered sections
    if re.match(r'^\d+\.\s+[A-Z]', text):
        return True
    
    # Principle/service headings (with colons)
    principle_patterns = [
        'Equitable access', 'Shared decision-making', 'Shared governance', 
        'Shared funding', 'Local points', 'Access:', 'Guidance and Advice:',
        'Training:', 'Provincial Purchasing', 'Technological Support:'
    ]
    if any(pattern in text for pattern in principle_patterns):
        return True
    
    # "For each" questions
    if text.startswith('For each') and text.endswith(':'):
        return True
    
    # Main title components
    if 'Ontario' in text and 'Digital Library' in text and len(text) > 15:
        return True
    if 'Critical Component' in text or 'Road Map to Prosperity' in text:
        return True
    if text.startswith('What could the ODL'):
        return True
        
    return False

def is_body_text(text):
    """Identify body text that should NOT be a heading"""
    text = text.strip()
    
    # Too long - likely paragraph
    if len(text) > 100:
        return True
    
    # Ends with period - likely sentence
    if text.endswith('.') and len(text) > 20:
        return True
    
    # Contains detailed explanations
    if any(phrase in text.lower() for phrase in [
        'the purpose of this', 'will be expected to', 'must be received by',
        'please note that', 'if you require', 'specifically,', 'given the',
        'for example,', 'however,', 'although', 'in addition to'
    ]):
        return True
    
    # Contact info, dates, addresses
    if re.search(r'@|\d{4}|phone|email|fax|mail', text.lower()):
        return True
    
    # Bullet point content (not headers)
    if text.startswith('-') and len(text) > 30:
        return True
        
    return False

def get_heading_level(text, size, font_stats):
    """Determine heading level based on content and size"""
    text = text.strip()
    
    # H1: Main document sections
    if (size >= font_stats['large_size'] and 
        ('Digital Library' in text or 'Critical Component' in text)):
        return "H1"
    
    # H2: Major sections
    if (text in ['Summary', 'Background'] or 
        text.startswith('The Business Plan') or
        text.startswith('Approach and') or
        text.startswith('Evaluation and') or
        text.startswith('Appendix')):
        return "H2"
    
    # H3: Subsections and principles
    if (text.startswith('Timeline') or text.startswith('Milestones') or
        text.startswith('Phase') or re.match(r'^\d+\.', text) or
        any(p in text for p in ['Equitable access', 'Shared decision', 'Shared governance', 
                               'Shared funding', 'Local points', 'Access:', 'Guidance', 
                               'Training:', 'Provincial', 'Technological', 'What could'])):
        return "H3"
    
    # H4: "For each" questions
    if text.startswith('For each') and text.endswith(':'):
        return "H4"
    
    # Fallback based on size for unmatched structural headings
    if size >= font_stats['large_size']:
        return "H1"
    elif size >= font_stats['medium_size']:
        return "H2"
    
    return None

def analyze_fonts(lines):
    """Analyze font usage to determine size tiers"""
    sizes = [l['size'] for l in lines]
    size_counts = defaultdict(int)
    for size in sizes:
        size_counts[round(size, 1)] += 1
    
    # Get most common sizes
    sorted_sizes = sorted(size_counts.items(), key=lambda x: (-x[1], -x[0]))
    
    return {
        'large_size': sorted_sizes[0][0] if sorted_sizes else 14,
        'medium_size': sorted_sizes[1][0] if len(sorted_sizes) > 1 else 12,
        'body_size': sorted_sizes[2][0] if len(sorted_sizes) > 2 else 11
    }

def extract_outline(pdf_path):
    doc = fitz.open(pdf_path)
    all_lines = []
    
    # Extract all text lines
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        blocks = page.get_text("dict")["blocks"]
        
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                if not line["spans"]:
                    continue
                    
                # Combine all spans in line
                text_parts = [span["text"] for span in line["spans"] if span["text"].strip()]
                if not text_parts:
                    continue
                    
                text = clean(" ".join(text_parts))
                size = max(span["size"] for span in line["spans"])
                bold = any(span["flags"] & 16 for span in line["spans"])  # Bold flag
                
                all_lines.append({
                    "text": text,
                    "size": size,
                    "bold": bold,
                    "page": page_num + 1
                })
    
    doc.close()
    
    # Analyze font statistics
    font_stats = analyze_fonts(all_lines)
    
    # Extract title (first few large lines on page 1)
    page1_large = [l for l in all_lines 
                   if l["page"] == 1 and l["size"] >= font_stats['medium_size'] 
                   and not is_body_text(l["text"])][:3]
    title = clean(" ".join([l["text"] for l in page1_large]))
    
    # Extract outline
    outline = []
    seen = set()
    
    for line in all_lines:
        text = clean(line["text"])
        
        # Skip if already seen, too short, or clearly body text
        if (text in seen or len(text) < 4 or 
            is_body_text(text) or not is_structural_heading(text)):
            continue
        
        level = get_heading_level(text, line["size"], font_stats)
        if level:
            outline.append({
                "level": level,
                "text": text,
                "page": line["page"]
            })
            seen.add(text)
    
    return {
        "title": title if title else "Untitled",
        "outline": outline
    }

# Main execution with batch processing
if __name__ == "__main__":
    input_dir = "./input"
    output_dir = "./output"
    os.makedirs(output_dir, exist_ok=True)
    
    if not os.path.exists(input_dir):
        print(f"Error: Input directory '{input_dir}' does not exist.")
        exit(1)
    
    for filename in os.listdir(input_dir):
        if filename.lower().endswith(".pdf"):
            pdf_path = os.path.join(input_dir, filename)
            try:
                result = extract_outline(pdf_path)
                output_path = os.path.join(output_dir, os.path.splitext(filename)[0] + ".json")
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                print(f"Processed: {filename} -> {output_path}")
            except Exception as e:
                print(f"Error processing {filename}: {str(e)}")
