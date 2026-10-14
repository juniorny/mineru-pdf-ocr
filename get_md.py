import os
import shutil

def collect_all_full_md(root_dir, output_dir="汇总_full_md"):
    """
    递归查找所有 full.md，并按【所在目录名.md】汇总到一个文件夹
    :param root_dir: 要扫描的根目录
    :param output_dir: 汇总输出文件夹
    """
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    collected = 0

    # 递归遍历所有文件
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            # 只找 full.md（大小写不敏感）
            if filename.lower() == "full.md":
                src_path = os.path.join(dirpath, filename)
                
                # 取【所在文件夹名】作为新文件名
                folder_name = os.path.basename(dirpath)
                new_filename = f"{folder_name}.md"
                dest_path = os.path.join(output_dir, new_filename)

                # 处理重名（自动加编号）
                counter = 1
                while os.path.exists(dest_path):
                    new_filename = f"{folder_name}_{counter}.md"
                    dest_path = os.path.join(output_dir, new_filename)
                    counter += 1

                # 复制文件
                shutil.copy2(src_path, dest_path)
                print(f"✅ 已汇总：{new_filename}")
                collected += 1

    print(f"\n🎉 全部完成！共找到并汇总 {collected} 个 full.md 文件")
    print(f"📁 所有文件保存在：{os.path.abspath(output_dir)}")

# ====================== 你只需要改这里 ======================
# 要扫描的根目录（填你的路径）
SCAN_ROOT = os.environ.get("SCAN_ROOT", r"./input")
# ===========================================================

if __name__ == "__main__":
    collect_all_full_md(SCAN_ROOT, output_dir = SCAN_ROOT + "\\汇总MD")