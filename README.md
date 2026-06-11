# 投标自查卫士使用与打包指南

## macOS 用户直接运行 (已编译)
1. 解压后，直接双击运行 `dist/投标自查卫士` 可执行文件。
2. 程序启动后会自动在系统默认浏览器中打开配置及审查界面 (http://localhost:8000)。
3. 该运行方式不需要安装 Python，也不需要安装任何依赖包。

## Windows 用户运行方式
由于在 macOS 环境下无法直接编译 Windows 可执行程序，Windows 用户有以下两种运行方式：

### 方式一：使用本地 Python 运行
1. 确保电脑已安装 Python 3。
2. 双击运行 `投标自查卫士.bat`。
3. 服务端启动后，程序会自动打开浏览器访问 http://localhost:8000。

### 方式二：在 Windows 本地打包为 exe 独立可执行程序
如果在无 Python 的 Windows 电脑上运行，可以找一台有 Python 环境的 Windows 电脑执行以下步骤打包：
1. 打开命令行 (CMD 或 PowerShell) 进入当前项目文件夹。
2. 安装打包工具及依赖包：
   pip install -r requirements.txt pyinstaller
3. 执行以下 PyInstaller 命令进行打包 (注意 Windows 下资源路径使用分号分隔)：
   pyinstaller --name="投标自查卫士" --add-data "index.html;." --add-data "logo.png;." --add-data "hualu_result.txt;." --add-data "zhizhenyun_result.txt;." --add-data "zhuowei_result.txt;." --onefile server.py
4. 打包完成后，在 dist 目录下会生成 `投标自查卫士.exe`。将其发送给其他 Windows 用户，双击即可无依赖运行。
