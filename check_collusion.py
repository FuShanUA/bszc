import os
import re
import sys
import argparse
import hashlib
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import pypdf

def clean_text(text):
    if not text:
        return ""
    # Keep only Chinese characters, letters, and numbers
    return re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', text)

def extract_bidder_name(pdf_path):
    try:
        reader = pypdf.PdfReader(pdf_path)
        for i in range(min(10, len(reader.pages))):
            text = reader.pages[i].extract_text()
            if not text:
                continue
            # Look for 投标人 patterns
            match = re.search(r'投标人\s*[:：\s]\s*([^\s\n\(\)（）]+)', text)
            if match:
                return match.group(1).strip()
            match = re.search(r'投标人\s*([^\s\n\(\)（）]+公司)', text)
            if match:
                return match.group(1).strip()
    except Exception:
        pass
    return os.path.splitext(os.path.basename(pdf_path))[0]

def simplify_bidder_name(name):
    if "华路" in name:
        return "华路"
    if "至臻云" in name:
        return "至臻云"
    if "卓维" in name:
        return "卓维"
    if "数据易" in name:
        return "数据易"
    cleaned = re.sub(r'^(北京|广东|上海|深圳|天津|重庆|四川|江苏|浙江|山东|福建|湖北|湖南|河南|河北|安徽|江西|陕西|辽宁|吉林|黑龙江|山西|甘肃|青海|海南|云南|贵州|广西|内蒙古|西藏|宁夏|新疆)', '', name)
    cleaned = re.sub(r'(股份有限公司|有限责任公司|有限公司|信息技术|智能科技|网络)$', '', cleaned)
    return cleaned

def classify_match(longest_match):
    template_indicators = [
        "按所投对应标的",
        "如不涉及本项内容则无需提供",
        "请根据技术规范要求",
        "注1投标人对招标文件",
        "注请根据",
        "无需提供",
        "如不涉及",
        "采购编号",
        "标的名称",
        "标包名称",
        "技术部分",
        "技术规范书",
        "投标偏差表",
        "所有条款条件及规定",
        "南方电网",
        "技术投标文件",
        "第一批信息化项目",
        "信息化项目",
        "注1",
        "采购项目",
        "盖公章",
        "电子印章",
        "法定代表人",
        "投标函",
        "投标人盖章"
    ]
    for indicator in template_indicators:
        if indicator in longest_match:
            return "标书模板内容未删除"
    return "文本内容抄袭"



def compare_metadata(primary_path, secondary_path):
    try:
        pri_reader = pypdf.PdfReader(primary_path)
        sec_reader = pypdf.PdfReader(secondary_path)
    except Exception as e:
        print(f"Error reading PDF metadata: {e}")
        return []
    
    pri_meta = pri_reader.metadata or {}
    sec_meta = sec_reader.metadata or {}
    
    matches = []
    fields_to_compare = [
        ('/Author', "作者"),
        ('/Creator', "创建程序"),
        ('/Producer', "PDF生成器"),
        ('/CreationDate', "创建时间"),
        ('/ModDate', "修改时间")
    ]
    
    for field, name in fields_to_compare:
        pri_val = pri_meta.get(field)
        sec_val = sec_meta.get(field)
        
        if pri_val and sec_val:
            pri_val_str = str(pri_val).strip()
            sec_val_str = str(sec_val).strip()
            
            if pri_val_str and sec_val_str and pri_val_str.lower() != 'none' and sec_val_str.lower() != 'none':
                if pri_val_str == sec_val_str:
                    # Same CreationDate or Author is very high suspicion
                    rate = 0.90 if field in ['/Author', '/CreationDate', '/ModDate'] else 0.40
                    matches.append({
                        "primary_pages": "全档",
                        "secondary_pages": "全档",
                        "suspicion_rate": rate,
                        "description": f"[属性一致] 两份标书的{name}相同: '{pri_val_str}'"
                    })
    return matches

def extract_images_from_pdf(pdf_path):
    image_hashes = defaultdict(list)
    try:
        reader = pypdf.PdfReader(pdf_path)
        for page_idx, page in enumerate(reader.pages):
            page_num = page_idx + 1
            try:
                # pypdf page.images collection
                for img_idx, img_obj in enumerate(page.images):
                    try:
                        try:
                            img_data = img_obj.data
                        except Exception:
                            try:
                                img_data = img_obj._data
                            except Exception:
                                continue
                        if not img_data:
                            continue
                        md5_hash = hashlib.md5(img_data).hexdigest()
                        image_hashes[md5_hash].append((page_num, img_obj.name))
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception as e:
        print(f"Error extracting images from {pdf_path}: {e}")
    return image_hashes

def compare_images(primary_path, secondary_path):
    pri_images = extract_images_from_pdf(primary_path)
    sec_images = extract_images_from_pdf(secondary_path)
    
    matches = []
    common_hashes = set(pri_images.keys()) & set(sec_images.keys())
    
    for h in common_hashes:
        pri_occurrences = pri_images[h]
        sec_occurrences = sec_images[h]
        
        pri_pages = sorted(list(set(p for p, _ in pri_occurrences)))
        sec_pages = sorted(list(set(p for p, _ in sec_occurrences)))
        
        pri_pages_str = ",".join(f"P{p}" for p in pri_pages)
        sec_pages_str = ",".join(f"P{p}" for p in sec_pages)
        
        matches.append({
            "primary_pages": pri_pages_str,
            "secondary_pages": sec_pages_str,
            "suspicion_rate": 0.95,
            "description": f"[配图一致] 两份标书含有完全相同的图片资源 (MD5: {h[:8]})"
        })
    return matches

def compare_text_pages(primary_path, secondary_path, ngram_size=15, min_match_len=20, sim_threshold=0.10):
    try:
        primary_reader = pypdf.PdfReader(primary_path)
        secondary_reader = pypdf.PdfReader(secondary_path)
    except Exception as e:
        print(f"Error loading PDFs for text comparison: {e}")
        return []
    
    print("正在提取主标书文本...")
    primary_pages = []
    for idx, page in enumerate(primary_reader.pages):
        raw = page.extract_text() or ""
        primary_pages.append(clean_text(raw))
        
    print("正在提取陪标书文本...")
    secondary_pages = []
    for idx, page in enumerate(secondary_reader.pages):
        raw = page.extract_text() or ""
        secondary_pages.append(clean_text(raw))
        
    # Index N-grams of secondary PDF to quickly filter candidate pages
    print("正在对陪标书建立N-gram索引...")
    sec_ngram_index = defaultdict(list)
    for sec_idx, sec_text in enumerate(secondary_pages):
        sec_page_num = sec_idx + 1
        if len(sec_text) < ngram_size:
            continue
        for i in range(len(sec_text) - ngram_size + 1):
            ngram = sec_text[i:i+ngram_size]
            sec_ngram_index[ngram].append(sec_page_num)
            
    print("正在匹配主标书文本片段...")
    candidates = defaultdict(int)
    for pri_idx, pri_text in enumerate(primary_pages):
        pri_page_num = pri_idx + 1
        if len(pri_text) < ngram_size:
            continue
        for i in range(len(pri_text) - ngram_size + 1):
            ngram = pri_text[i:i+ngram_size]
            if ngram in sec_ngram_index:
                for sec_page_num in sec_ngram_index[ngram]:
                    candidates[(pri_page_num, sec_page_num)] += 1

    results = []
    total_candidates = len(candidates)
    print(f"筛选出 {total_candidates} 个候选重合页面对，进行详细比对...")
    
    count = 0
    for (pri_page, sec_page), common_count in candidates.items():
        count += 1
        if count % 100 == 0:
            print(f"比对进度: {count}/{total_candidates}...")
            
        # If very few matching N-grams, skip detailed diff to save time
        if common_count < 3:
            continue
            
        pri_text = primary_pages[pri_page - 1]
        sec_text = secondary_pages[sec_page - 1]
        
        matcher = SequenceMatcher(None, pri_text, sec_text)
        matching_blocks = matcher.get_matching_blocks()
        
        total_match_len = 0
        longest_match = ""
        
        for block in matching_blocks:
            if block.size >= min_match_len:
                total_match_len += block.size
                match_str = pri_text[block.a : block.a + block.size]
                if len(match_str) > len(longest_match):
                    longest_match = match_str
                    
        if total_match_len > 0:
            min_len = min(len(pri_text), len(sec_text))
            susp_rate = total_match_len / min_len if min_len > 0 else 0
            
            if susp_rate >= sim_threshold:
                match_type = classify_match(longest_match)
                if match_type == "标书模板内容未删除":
                    desc = f"标书模板内容未删除。匹配: '{longest_match[:30]}...'"
                    reported_susp_rate = susp_rate * 0.10
                else:
                    desc = f"文本内容高相似。最长匹配: '{longest_match[:30]}...'"
                    reported_susp_rate = susp_rate
                results.append({
                    "primary_page": pri_page,
                    "secondary_page": sec_page,
                    "suspicion_rate": reported_susp_rate,
                    "description": desc,
                    "match_type": match_type
                })
                
    return results

def group_text_matches(matches):
    if not matches:
        return []
    
    # Sort matches by primary_page
    matches = sorted(matches, key=lambda x: (x['match_type'], x['primary_page'], x['secondary_page']))
    
    grouped = []
    current = None
    
    for m in matches:
        if current is None:
            current = {
                "match_type": m["match_type"],
                "primary_start": m["primary_page"],
                "primary_end": m["primary_page"],
                "secondary_start": m["secondary_page"],
                "secondary_end": m["secondary_page"],
                "rates": [m["suspicion_rate"]],
                "descriptions": [m["description"]]
            }
        else:
            # Check if contiguous pages
            if (m["match_type"] == current["match_type"] and
                m["primary_page"] == current["primary_end"] + 1 and
                m["secondary_page"] == current["secondary_end"] + 1):
                current["primary_end"] = m["primary_page"]
                current["secondary_end"] = m["secondary_page"]
                current["rates"].append(m["suspicion_rate"])
                current["descriptions"].append(m["description"])
            else:
                grouped.append(current)
                current = {
                    "match_type": m["match_type"],
                    "primary_start": m["primary_page"],
                    "primary_end": m["primary_page"],
                    "secondary_start": m["secondary_page"],
                    "secondary_end": m["secondary_page"],
                    "rates": [m["suspicion_rate"]],
                    "descriptions": [m["description"]]
                }
    if current:
        grouped.append(current)
        
    formatted_grouped = []
    for g in grouped:
        max_rate = max(g["rates"])
        
        if g["primary_start"] == g["primary_end"]:
            pri_range = f"P{g['primary_start']}"
        else:
            pri_range = f"P{g['primary_start']}-P{g['primary_end']}"
            
        if g["secondary_start"] == g["secondary_end"]:
            sec_range = f"P{g['secondary_start']}"
        else:
            sec_range = f"P{g['secondary_start']}-P{g['secondary_end']}"
            
        if len(g["descriptions"]) == 1:
            desc = g["descriptions"][0]
        else:
            desc = f"连续{len(g['descriptions'])}页文本匹配。第一匹配段: {g['descriptions'][0]}"
            
        formatted_grouped.append({
            "primary_pages": pri_range,
            "secondary_pages": sec_range,
            "suspicion_rate": max_rate,
            "description": f"[{g['match_type']}] {desc}"
        })
        
    return formatted_grouped

def main():
    parser = argparse.ArgumentParser(description="投标书串标自查比对工具")
    parser.add_argument("--primary", required=True, help="主标书 PDF 路径")
    parser.add_argument("--secondary", required=True, help="陪标书 PDF 路径")
    parser.add_argument("--threshold", type=float, default=0.10, help="文本相似度阈值 (默认: 0.10)")
    args = parser.parse_args()
    
    if not os.path.exists(args.primary):
        print(f"错误: 主标书路径不存在: {args.primary}")
        sys.exit(1)
        
    if not os.path.exists(args.secondary):
        print(f"错误: 陪标书路径不存在: {args.secondary}")
        sys.exit(1)
        
    print("=" * 60)
    print("投标书串标自查比对开始...")
    
    # 提取投标人名称
    primary_bidder = extract_bidder_name(args.primary)
    secondary_bidder = extract_bidder_name(args.secondary)
    
    print(f"主标投标人: {primary_bidder}")
    print(f"陪标投标人: {secondary_bidder}")
    print("=" * 60)
    
    all_results = []
    
    # 1. 属性比对
    print("正在比对文档属性/元数据...")
    meta_results = compare_metadata(args.primary, args.secondary)
    all_results.extend(meta_results)
    
    # 2. 图片比对
    print("正在比对图片资源...")
    image_results = compare_images(args.primary, args.secondary)
    all_results.extend(image_results)
    
    # 3. 文本比对
    print("正在比对文本相似度...")
    text_results = compare_text_pages(args.primary, args.secondary, sim_threshold=args.threshold)
    grouped_text = group_text_matches(text_results)
    all_results.extend(grouped_text)
    
    # 排序
    all_results = sorted(all_results, key=lambda x: x["suspicion_rate"], reverse=True)
    
    # 输出结果
    print("\n" + "=" * 80)
    print(f"比对结果列表 (按嫌疑率降序): 主标[{simplify_bidder_name(primary_bidder)}] vs 陪标[{simplify_bidder_name(secondary_bidder)}]")
    print("-" * 80)
    
    if not all_results:
        print("未检测到明显的串标疑似内容。")
    else:
        # Markdown table
        print("| 序号 | 陪标单位 | 陪标页码 | 主标页码 | 嫌疑疑似率 | 问题描述 |")
        print("| --- | --- | --- | --- | --- | --- |")
        for idx, item in enumerate(all_results, 1):
            rate_str = f"{item['suspicion_rate'] * 100:.1f}%"
            print(f"| {idx} | {simplify_bidder_name(secondary_bidder)} | {item['secondary_pages']} | {item['primary_pages']} | {rate_str} | {item['description']} |")
            
    print("=" * 80)

if __name__ == "__main__":
    main()
