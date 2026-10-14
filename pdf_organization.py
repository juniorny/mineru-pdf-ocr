import os
import shutil
from PyPDF2 import PdfReader

# ===================== 配置参数（可根据需求修改）=====================
# 源文件夹路径（存放待整理的所有PDF）
SOURCE_DIR = os.environ.get("SOURCE_DIR", r"./input")
# 超页数文件夹路径
OVER_PAGE_DIR = f"{SOURCE_DIR}/超页数PDF"
# 超大小文件夹路径
OVER_SIZE_DIR = f"{SOURCE_DIR}/超大小PDF"
# 合格PDF存放根路径
VALID_PDF_DIR = f"{SOURCE_DIR}/合格PDF"
# 最大页数限制
MAX_PAGE = 200
# 最大文件大小限制（单位：MB，自动转换为字节）
MAX_SIZE_MB = 200
MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024
# 每批次存放的最大PDF数量
BATCH_COUNT = 50
# =================================================================

def create_dir_if_not_exists(dir_path):
    """如果文件夹不存在，则创建"""
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

def get_pdf_page_count(pdf_path):
    """获取PDF文件的页数，处理损坏/无法读取的PDF"""
    try:
        with open(pdf_path, 'rb') as f:
            reader = PdfReader(f)
            return len(reader.pages)
    except Exception as e:
        print(f"⚠️  读取PDF页数失败（文件可能损坏）：{pdf_path}，错误：{str(e)}")
        return -1  # 读取失败返回-1

def move_file(src_file, target_dir):
    """移动文件到目标文件夹，处理重名文件"""
    file_name = os.path.basename(src_file)
    target_path = os.path.join(target_dir, file_name)
    
    # 处理重名文件
    if os.path.exists(target_path):
        name, ext = os.path.splitext(file_name)
        count = 1
        while True:
            new_name = f"{name}_{count}{ext}"
            target_path = os.path.join(target_dir, new_name)
            if not os.path.exists(target_path):
                break
            count += 1
    
    shutil.move(src_file, target_path)
    print(f"✅ 已移动：{file_name} -> {target_dir}")

def batch_move_files(file_list, target_root_dir, batch_size):
    """批量移动文件，按指定数量分文件夹存放"""
    if not file_list:
        return
    
    # 计算需要创建的文件夹数量
    total_files = len(file_list)
    folder_num = (total_files + batch_size - 1) // batch_size  # 向上取整
    
    for i in range(folder_num):
        # 创建批次文件夹（如：批次1、批次2）
        batch_folder = os.path.join(target_root_dir, f"批次{i+1}")
        create_dir_if_not_exists(batch_folder)
        
        # 截取当前批次的文件列表
        start_idx = i * batch_size
        end_idx = start_idx + batch_size
        current_batch = file_list[start_idx:end_idx]
        
        # 移动文件
        for pdf in current_batch:
            move_file(pdf, batch_folder)
    
    print(f"\n📦 合格PDF已分{folder_num}个批次存放，每批次最多{batch_size}个")

def organize_pdf_files():
    """主函数：PDF文件整理逻辑"""
    # 1. 创建所有需要的文件夹
    create_dir_if_not_exists(SOURCE_DIR)
    create_dir_if_not_exists(OVER_PAGE_DIR)
    create_dir_if_not_exists(OVER_SIZE_DIR)
    create_dir_if_not_exists(VALID_PDF_DIR)
    
    # 存储合格的PDF文件路径
    valid_pdf_list = []
    
    print("="*50)
    print("开始扫描并整理PDF文件...")
    print("="*50)
    
    # 2. 遍历源文件夹所有文件
    for file_name in os.listdir(SOURCE_DIR):
        # 只处理PDF文件（忽略大小写）
        if not file_name.lower().endswith(".pdf"):
            continue
        
        pdf_path = os.path.join(SOURCE_DIR, file_name)
        # 跳过文件夹（防止子目录干扰）
        if not os.path.isfile(pdf_path):
            continue
        
        print(f"\n正在处理：{file_name}")
        
        # 3. 第一步：检查页数
        page_count = get_pdf_page_count(pdf_path)
        if page_count > MAX_PAGE:
            move_file(pdf_path, OVER_PAGE_DIR)
            continue
        
        # 页数读取失败的文件，不加入合格列表
        if page_count == -1:
            continue
        
        # 4. 第二步：检查文件大小
        file_size = os.path.getsize(pdf_path)
        if file_size > MAX_SIZE_BYTES:
            move_file(pdf_path, OVER_SIZE_DIR)
            continue
        
        # 5. 符合所有条件，加入合格列表
        valid_pdf_list.append(pdf_path)
        print(f"✅ 符合要求，加入合格列表")
    
    # 6. 第三步：合格PDF批量分文件夹
    batch_move_files(valid_pdf_list, VALID_PDF_DIR, BATCH_COUNT)
    
    print("\n" + "="*50)
    print("🎉 PDF文件整理完成！")
    print(f"📄 合格PDF总数：{len(valid_pdf_list)}")
    print(f"📂 超页数文件：{len(os.listdir(OVER_PAGE_DIR))} 个")
    print(f"📂 超大小文件：{len(os.listdir(OVER_SIZE_DIR))} 个")
    print("="*50)

if __name__ == "__main__":
    organize_pdf_files()