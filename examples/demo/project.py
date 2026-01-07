import sys,os

# Check and create build/config/global_config.mk file
# Get the directory where the current script is located
current_dir = os.path.dirname(os.path.abspath(__file__))
# Get full path of build/config/global_config.mk
global_config_path = os.path.join(current_dir, "build", "config", "global_config.mk")

# Check if the file exists, create it if not
if not os.path.exists(global_config_path):
    # Create build/config folder (if not exists)
    config_dir = os.path.dirname(global_config_path)
    os.makedirs(config_dir, exist_ok=True)
    # Create empty global_config.mk file
    with open(global_config_path, 'w', encoding='utf-8') as f:
        pass  # Write empty content
    print(f"-- Created empty file: {global_config_path}")
else:
    print(f"-- File already exists: {global_config_path}")

CONFIG_BUILD_WHL_PACKAGE = 0
config_value = None
with open(global_config_path, 'r', encoding='utf-8') as f:
    for line_num, line in enumerate(f, 1):
        # 去除行首尾的空白字符（空格、制表符、换行符等）
        clean_line = line.strip()
        
        # 查找以 CONFIG_BUILD_WHL_PACKAGE= 开头的行
        if clean_line.startswith('CONFIG_BUILD_WHL_PACKAGE='):
            # 分割配置项和值
            key, value = clean_line.split('=', 1)  # 只分割第一个等号
            config_value = value.strip()
            break

    # 判断配置值是否为 y
    if config_value == 'y':
        CONFIG_BUILD_WHL_PACKAGE = 1
    else:
        CONFIG_BUILD_WHL_PACKAGE = 0
print(f"CONFIG_BUILD_WHL_PACKAGE={CONFIG_BUILD_WHL_PACKAGE}")




# Original code part
sdk_env_name = "MY_SDK_PATH"
custom_component_path_name = "CUSTOM_COMPONENTS_PATH"

# Get SDK absolute path
sdk_path = os.path.abspath(os.path.join(sys.path[0], "../../"))
try:
    # Check if environment variable exists first, then check if path exists
    env_sdk_path = os.environ.get(sdk_env_name)
    if env_sdk_path and os.path.exists(env_sdk_path):
        sdk_path = env_sdk_path
except Exception as e:
    print(f"-- Error getting SDK path environment variable: {e}")
print(f"-- SDK_PATH:{sdk_path}")

# Get custom components path
custom_components_path = None
try:
    # Optimization: Use get method to avoid KeyError, more elegant
    env_custom_path = os.environ.get(custom_component_path_name)
    if env_custom_path and os.path.exists(env_custom_path):
        custom_components_path = env_custom_path
except Exception as e:
    print(f"-- Error getting custom component path environment variable: {e}")
print(f"-- CUSTOM_COMPONENTS_PATH:{custom_components_path}")



if len(sys.argv) >= 2 and CONFIG_BUILD_WHL_PACKAGE == 1:
    if sys.argv[1] == "rebuild" or sys.argv[1] == "build":
        cpp_bind_path = os.path.join(current_dir, "cpp_bind_python.py")
        os.chdir(current_dir)  # 切换到cpp_bind_python.py所在目录
        with open(cpp_bind_path, 'r', encoding='utf-8') as f:
            exec(f.read())
        project_file_path = os.path.join(sdk_path, "tools", "cmake", "project.py")
        with open(project_file_path, 'r', encoding='utf-8') as f:
            exec(f.read())
        setup_path = os.path.join(current_dir, "setup.py")
        # original_cwd = os.getcwd()
        os.chdir(current_dir)  # 切换到setup.py所在目录
        with open(setup_path, 'r', encoding='utf-8') as f:
            sys.argv = ['setup.py', 'bdist_wheel']
            exec(f.read())
        # os.chdir(original_cwd)  # 恢复原工作目录（可选但规范）
        sys.exit(1)


# Execute project script from SDK
project_file_path = os.path.join(sdk_path, "tools", "cmake", "project.py")
try:
    with open(project_file_path, 'r', encoding='utf-8') as f:
        exec(f.read())
except FileNotFoundError:
    print(f"-- Error: project.py file not found - {project_file_path}")
    sys.exit(1)
except Exception as e:
    print(f"-- Error executing project.py: {e}")
    sys.exit(1)