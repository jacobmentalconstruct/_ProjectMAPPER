# 🚀 ProjectMAPPER

**ProjectMAPPER** is a simple, standalone desktop tool designed to help you analyze, audit, and back up a software project. It's a single Python script with a graphical user interface that runs on Windows, macOS, and Linux without any external dependencies.

Just drop it into your project directory and run it!

![ProjectMAPPER Screenshot](https://i.imgur.com/your-screenshot-url.png)
*(To add a screenshot: take a picture of your app, upload it to a host like [Imgur](https://imgur.com), and paste the link here.)*

## Features

* **Interactive Project Tree:** Visualize your project's folder structure. Interactively check or uncheck folders to include or exclude them from all operations.
* **Generate Text Maps:** Create a clean text file that maps out the directory and file structure of all selected items.
* **Dump Source Code:** Concatenate the contents of all selected text-based files into a single, comprehensive `.txt` file for easy review or sharing.
* **System & Environment Audits:**
    * **System Info:** Log details about your OS, Python version, and installed packages (`pip freeze`).
    * **Conda Environments:** List all available Conda environments and audit the packages within a selected environment.
* **Project Backup:** Create a compressed `.tar.gz` archive of all selected files and folders—perfect for creating a snapshot of your work.
* **Configuration persistence:** The tool saves your folder selections and custom file exclusions for each project, so your setup is remembered next time you run it.
* **No Installation Needed:** Runs on any system with a standard Python 3 installation.

## How to Use

Choose the instructions for your operating system.

### ▶️ On Windows

1.  Place the `_ProjectMAPPER` folder inside your project directory.
2.  Open the `_ProjectMAPPER` folder and double-click the **`pm.bat`** file to start the application.

### ▶️ On macOS or Linux (Ubuntu, etc.)

**First-Time Setup (One-Time Only):**
Before running the script for the first time, you need to make it executable. You only have to do this once.

1.  Open your **Terminal** application.
2.  Navigate into the `_ProjectMAPPER` folder.
3.  Run the following command and press Enter:
    ```sh
    chmod +x pm.sh
    ```

**Running the Application:**
1.  Double-click the **`pm.sh`** file.
2.  If prompted, choose **"Run in Terminal"** or **"Run"**. On macOS, you may need to right-click, select "Open With," and choose "Terminal.app".

## How It Works

This application is built with Python and its standard `tkinter` library for the graphical user interface. It is intentionally kept as a single, self-contained script to ensure it is portable and requires no setup.