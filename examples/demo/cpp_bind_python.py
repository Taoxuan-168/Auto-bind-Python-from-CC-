#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动解析带@module注释的C++头文件，生成pybind11绑定代码和pyi存根文件
"""
import re
import os
import sys
import shutil


# 从build/config/global_config.mk读取whl包名称 
current_dir = os.path.dirname(os.path.abspath(__file__))
global_config_path = os.path.join(current_dir, "build", "config", "global_config.mk")
config_value = None
with open(global_config_path, 'r', encoding='utf-8') as f:
    for line_num, line in enumerate(f, 1):
        # 去除行首尾的空白字符（空格、制表符、换行符等）
        clean_line = line.strip()
        
        # 查找以 CONFIG_WHL_PACKAGE_NAME= 开头的行
        if clean_line.startswith('CONFIG_WHL_PACKAGE_NAME='):
            # 分割配置项和值
            key, value = clean_line.split('=', 1)  # 只分割第一个等号
            # 先去除值两端的空白，再去除两端的双引号
            config_value = value.strip().strip('"')
            break

# ===================== 配置项 =====================
TARGET_HEADER_FILE = f"main/include/{config_value}.hpp"  # 自动寻找.hpp
OUTPUT_BIND_FILE = "main/src/bind.cpp"     # 生成的pybind11绑定代码输出路径
MAIN_MODULE_NAME = config_value            # Python主模块名
# Stub文件输出目录（脚本同目录的build/stub）
STUB_OUTPUT_ROOT = os.path.join(current_dir, "build", "stub")
# ==================================================

def get_target_header_file(file_path):
    """
    验证并获取指定的单个头文件路径
    :param file_path: 目标头文件路径
    :return: 验证后的头文件路径
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"指定的头文件不存在: {file_path}")
    
    
    return file_path

def parse_module_annotations(header_file):
    """
    解析单个C++头文件中带@module注释的函数和类
    :param header_file: 待解析的C++头文件路径
    :return: 解析后的函数/类信息列表
    """
    if not os.path.exists(header_file):
        raise FileNotFoundError(f"头文件不存在: {header_file}")

    # 扩展正则：支持匹配类和类内方法（新增类解析逻辑）
    # 1. 匹配类的正则
    class_pattern = re.compile(
        r'namespace\s+([\w:]+)\s*\{\s*'          # 命名空间
        r'/\*\*([\s\S]*?)\*/\s+'                 # 类注释块
        r'class\s+(\w+)\s*\{[\s\S]*?\};'          # 类定义
        r'\}',                                   # 命名空间结束
        re.DOTALL | re.MULTILINE
    )
    
    # 2. 匹配函数（原有逻辑，保留）
    func_pattern = re.compile(
        r'namespace\s+([\w:]+)\s*\{\s*'          # 匹配命名空间（如add::test）
        r'/\*\*([\s\S]*?)\*/\s+'                 # 匹配注释块（兼容多行）
        r'(\w+)\s+(\w+)\(([\s\S]*?)\);\s*'       # 匹配函数返回值、函数名、参数
        r'\}',                                   # 匹配命名空间结束
        re.DOTALL | re.MULTILINE                # 关键：DOTALL让.匹配换行，MULTILINE匹配多行
    )

    # 3. 匹配类内方法的正则
    method_pattern = re.compile(
        r'class\s+(\w+)\s*\{[\s\S]*?'
        r'/\*\*([\s\S]*?)\*/\s+'
        r'(\w+)\s+(\w+)\(([\s\S]*?)\);'
        r'[\s\S]*?\};',
        re.DOTALL | re.MULTILINE
    )

    items = []  # 存储函数+类信息
    try:
        with open(header_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # ========== 第一步：解析全局函数（原有逻辑） ==========
        func_matches = func_pattern.findall(content)
        for match in func_matches:
            namespace, comment_block, return_type, func_name, params_str = match
            
            # 预处理注释块
            cleaned_comment = re.sub(r'^\s*\*+', '', comment_block, flags=re.MULTILINE)
            cleaned_comment = re.sub(r'^/\*\*|\*/$', '', cleaned_comment, flags=re.MULTILINE)
            cleaned_comment = re.sub(r'\s+', ' ', cleaned_comment).strip()

            # 提取@module
            module_match = re.search(r'@module\s+([\w.]+)', cleaned_comment)
            if not module_match:
                continue
            module_path = module_match.group(1).strip()

            # 提取函数描述
            desc_match = re.search(r'^(.*?)(?=\s*@param|\s*@return|\s*@module)', cleaned_comment)
            desc = desc_match.group(1).strip() if desc_match else ""

            # 提取返回值描述
            return_match = re.search(r'@return\s+([^@]+)', cleaned_comment)
            return_desc = return_match.group(1).strip() if return_match else ""

            # 提取参数信息
            params = []
            param_matches = re.findall(r'@param\s+(\w+)\s+([^@]+)', cleaned_comment)
            raw_params = []
            for p in params_str.split(','):
                p = p.strip()
                if p:
                    parts = p.rsplit(' ', 1)
                    if len(parts) == 2:
                        raw_params.append((parts[0].strip(), parts[1].strip()))

            for idx, (param_name, param_desc) in enumerate(param_matches):
                if idx >= len(raw_params):
                    break
                param_type = raw_params[idx][0]
                params.append({
                    "name": param_name.strip(),
                    "type": param_type,
                    "desc": param_desc.strip()
                })

            # 封装函数信息（标记类型为function）
            items.append({
                "type": "function",
                "namespace": namespace.strip(),
                "name": func_name.strip(),
                "return_type": return_type.strip(),
                "params": params,
                "module_path": module_path,
                "desc": desc,
                "return_desc": return_desc,
                "source_file": header_file
            })
        
        # ========== 第二步：解析类和类内方法（新增逻辑） ==========
        class_matches = class_pattern.findall(content)
        for match in class_matches:
            namespace, comment_block, class_name = match
            
            # 预处理类注释块
            cleaned_comment = re.sub(r'^\s*\*+', '', comment_block, flags=re.MULTILINE)
            cleaned_comment = re.sub(r'^/\*\*|\*/$', '', cleaned_comment, flags=re.MULTILINE)
            cleaned_comment = re.sub(r'\s+', ' ', cleaned_comment).strip()

            # 提取类的@module
            module_match = re.search(r'@module\s+([\w.]+)', cleaned_comment)
            if not module_match:
                continue
            module_path = module_match.group(1).strip()

            # 提取类描述
            class_desc = re.search(r'^(.*?)(?=\s*@param|\s*@module)', cleaned_comment)
            class_desc = class_desc.group(1).strip() if class_desc else ""

            # 解析类内方法
            class_content = re.search(r'class\s+' + re.escape(class_name) + r'\s*\{([\s\S]*?)\};', content)
            methods = []
            if class_content:
                # 在类内容中匹配方法
                method_matches = re.findall(
                    r'/\*\*([\s\S]*?)\*/\s+(\w+)\s+(\w+)\(([\s\S]*?)\);',
                    class_content.group(1),
                    re.DOTALL | re.MULTILINE
                )
                for meth_comment, meth_return, meth_name, meth_params in method_matches:
                    # 预处理方法注释
                    meth_clean_comment = re.sub(r'^\s*\*+', '', meth_comment, flags=re.MULTILINE)
                    meth_clean_comment = re.sub(r'^/\*\*|\*/$', '', meth_clean_comment, flags=re.MULTILINE)
                    meth_clean_comment = re.sub(r'\s+', ' ', meth_clean_comment).strip()

                    # 提取方法描述和参数
                    meth_desc = re.search(r'^(.*?)(?=\s*@param|\s*@return)', meth_clean_comment)
                    meth_desc = meth_desc.group(1).strip() if meth_desc else ""
                    
                    meth_return_desc = re.search(r'@return\s+([^@]+)', meth_clean_comment)
                    meth_return_desc = meth_return_desc.group(1).strip() if meth_return_desc else ""

                    # 解析方法参数
                    meth_params_list = []
                    meth_param_matches = re.findall(r'@param\s+(\w+)\s+([^@]+)', meth_clean_comment)
                    raw_meth_params = []
                    for p in meth_params.split(','):
                        p = p.strip()
                        if p:
                            parts = p.rsplit(' ', 1)
                            if len(parts) == 2:
                                raw_meth_params.append((parts[0].strip(), parts[1].strip()))

                    for idx, (param_name, param_desc) in enumerate(meth_param_matches):
                        if idx >= len(raw_meth_params):
                            break
                        param_type = raw_meth_params[idx][0]
                        meth_params_list.append({
                            "name": param_name.strip(),
                            "type": param_type,
                            "desc": param_desc.strip()
                        })

                    methods.append({
                        "name": meth_name.strip(),
                        "return_type": meth_return.strip(),
                        "params": meth_params_list,
                        "desc": meth_desc,
                        "return_desc": meth_return_desc
                    })

            # 封装类信息（标记类型为class）
            items.append({
                "type": "class",
                "namespace": namespace.strip(),
                "name": class_name.strip(),
                "module_path": module_path,
                "desc": class_desc,
                "methods": methods,
                "source_file": header_file
            })

    except Exception as e:
        print(f"解析文件 {header_file} 时出错: {e}")
    
    return items

def generate_pybind11_bind_code(functions, main_module=MAIN_MODULE_NAME, header_file=None):
    """
    生成pybind11绑定代码（兼容类和函数）
    :param functions: 解析后的函数/类信息列表
    :param main_module: Python主模块名
    :param header_file: 单个头文件路径
    :return: 绑定代码字符串
    """
    # 获取需要包含的头文件（单个文件）
    header_filename = os.path.basename(header_file) if header_file else ""
    
    # 绑定代码头部
    bind_code = f"""// 自动生成的pybind11绑定代码，请勿手动修改
#include <pybind11/pybind11.h>
"""
    # 包含目标头文件
    if header_filename:
        bind_code += f'#include "{header_filename}"\n'
    
    bind_code += f"""
namespace py = pybind11;

PYBIND11_MODULE({main_module}, m) {{
    m.doc() = "Auto bind from C/C++";

"""

    # 按Python子模块分组（如add.test → 子模块test）
    module_map = {}
    for item in functions:
        py_path_parts = item["module_path"].split('.')
        if len(py_path_parts) < 2:
            sub_module = ""
            py_name = py_path_parts[0] if py_path_parts else item["name"]
        else:
            sub_module = '.'.join(py_path_parts[1:-1])
            py_name = py_path_parts[-1]

        if sub_module not in module_map:
            module_map[sub_module] = {"functions": [], "classes": []}
        
        if item["type"] == "function":
            module_map[sub_module]["functions"].append({
                "cpp_func": f"{item['namespace']}::{item['name']}",
                "py_func": py_name,
                "params": item["params"],
                "desc": item["desc"]
            })
        elif item["type"] == "class":
            module_map[sub_module]["classes"].append({
                "cpp_class": f"{item['namespace']}::{item['name']}",
                "py_class": py_name,
                "desc": item["desc"],
                "methods": item["methods"]
            })

    # 生成子模块和绑定代码
    for sub_module, items in module_map.items():
        if sub_module:
            sub_module_chain = sub_module.split('.')
            parent = "m"
            for idx, sub in enumerate(sub_module_chain):
                var_name = f"submod_{'_'.join(sub_module_chain[:idx+1])}"
                bind_code += f"    auto {var_name} = {parent}.def_submodule(\"{sub}\", \"{sub_module} submodule\");\n"
                parent = var_name
            submod_var = parent
        else:
            submod_var = "m"

        # 绑定函数
        for func in items["functions"]:
            py_args = []
            for param in func["params"]:
                py_args.append(f'py::arg("{param["name"]}")')
            py_args_str = ", ".join(py_args) if py_args else ""

            bind_code += f"    // 绑定函数: {func['py_func']}\n"
            bind_code += f"    {submod_var}.def(\"{func['py_func']}\", &{func['cpp_func']}, "
            if py_args_str:
                bind_code += py_args_str + ", "
            bind_code += f'"{func["desc"]}");\n'
        
        # 绑定类
        for cls in items["classes"]:
            bind_code += f"    // 绑定类: {cls['py_class']}\n"
            bind_code += f"    py::class_<{cls['cpp_class']}> {cls['py_class']}_cls({submod_var}, \"{cls['py_class']}\", \"{cls['desc']}\");\n"
            
            # 绑定类方法
            for method in cls["methods"]:
                py_args = []
                for param in method["params"]:
                    py_args.append(f'py::arg("{param["name"]}")')
                py_args_str = ", ".join(py_args) if py_args else ""
                
                bind_code += f"    {cls['py_class']}_cls.def(\"{method['name']}\", &{cls['cpp_class']}::{method['name']}, "
                if py_args_str:
                    bind_code += py_args_str + ", "
                bind_code += f'"{method["desc"]}");\n'

    # 绑定代码尾部
    bind_code += """
}
"""
    return bind_code


def print_full_item_info(items):
    """
    打印解析到的所有函数/类详细信息
    :param items: 解析后的函数/类信息列表
    """
    print("\n" + "="*80)
    print("解析到的内容详细信息:")
    print("="*80)
    
    for idx, item in enumerate(items, 1):
        print(f"\n【{item['type']} {idx}】")
        print(f"  来源文件: {item['source_file']}")
        print(f"  命名空间: {item['namespace']}")
        print(f"  名称: {item['name']}")
        print(f"  模块路径: {item['module_path']}")
        print(f"  描述: {item['desc']}")
        
        if item['type'] == "function":
            print(f"  返回值类型: {item['return_type']}")
            print(f"  返回值描述: {item['return_desc']}")
            print(f"  参数列表:")
            if item['params']:
                for param in item['params']:
                    print(f"    - 名称: {param['name']}")
                    print(f"      类型: {param['type']}")
                    print(f"      描述: {param['desc']}")
            else:
                print(f"    (无参数)")
        
        elif item['type'] == "class":
            print(f"  类方法列表:")
            if item['methods']:
                for method in item['methods']:
                    print(f"    - 方法名: {method['name']}")
                    print(f"      返回值: {method['return_type']}")
                    print(f"      描述: {method['desc']}")
                    if method['params']:
                        print(f"      参数:")
                        for param in method['params']:
                            print(f"        - {param['name']}: {param['type']} ({param['desc']})")
            else:
                print(f"    (无方法)")
    
    print("\n" + "="*80)

def main():
    """主函数：读取指定单个头文件，解析并生成绑定代码和stub文件"""
    try:
        # 1. 验证并获取指定的单个头文件
        print(f"正在验证指定的头文件: {TARGET_HEADER_FILE}")
        target_file = get_target_header_file(TARGET_HEADER_FILE)
        print(f"验证通过，目标头文件: {target_file}")
        
        # 2. 解析该头文件
        print(f"\n正在解析头文件: {target_file}")
        all_items = parse_module_annotations(target_file)
        print(f"  从该文件解析到 {len(all_items)} 个带@module注释的项（函数/类）")
        
        if not all_items:
            print("\n未找到任何带@module注释的函数/类！")
            return
        
        # 打印详细信息
        print_full_item_info(all_items)

        # 3. 生成绑定代码
        print(f"总共找到 {len(all_items)} 个待绑定项，生成pybind11代码...")
        bind_code = generate_pybind11_bind_code(all_items, header_file=target_file)

        # 4. 写入绑定代码文件
        with open(OUTPUT_BIND_FILE, 'w', encoding='utf-8') as f:
            f.write(bind_code)
        print(f"绑定代码已生成到: {os.path.abspath(OUTPUT_BIND_FILE)}")

        # 5. 生成并写入stub文件（保留原有占位）
        
    except Exception as e:
        print(f"执行失败: {e}")
        raise

if __name__ == "__main__":
    main()