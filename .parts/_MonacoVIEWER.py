import sys
import os
import argparse
import json
import base64
import html
import contextlib
import re
import tkinter as tk # Kept for contract compliance, though primary GUI is pywebview

# --- DEPENDENCY CHECKS ---
# Force Qt backend for stability as per original source 
os.environ['PYWEBVIEW_GUI'] = 'qt'
os.environ.setdefault('PYWEBVIEW_LOG', 'info')

try:
    import qtpy
    from PySide6 import QtCore
    from PySide6.QtGui import QIcon
except ImportError as e:
    print(f"[fatal] Qt backend not available. Install: pip install qtpy PySide6\n{e}", file=sys.stderr)
    sys.exit(1)

try:
    import webview
    from webview import FileDialog
    from webview.menu import Menu, MenuAction, MenuSeparator
except ImportError as e:
    print(f"[fatal] pywebview not available. Install: pip install pywebview\n{e}", file=sys.stderr)
    sys.exit(1)

# --- LOG FILTERING (From legacy start_app.py) ---
def apply_log_filter():
    """Suppress harmless Mesa/Qt warnings often seen on Linux."""
    error_patterns = [
        re.compile(r"MESA-LOADER: failed to open i965"),
        re.compile(r"failed to load driver: i965"),
        re.compile(r"Buffer handle is null"),
        re.compile(r"Creation of StagingBuffer's SharedImage failed"),
        re.compile(r"shared_image_interface_proxy.cc"),
        re.compile(r"one_copy_raster_buffer_provider.cc"),
    ]

    class LogFilter:
        def __init__(self, stream):
            self.stream = stream
        def write(self, data):
            modified = data
            for pattern in error_patterns:
                if pattern.search(data):
                    modified = data.replace("ERROR", "WARNING (safe to ignore)")
                    modified = modified.replace("failed", "note: failed")
                    break
            self.stream.write(modified)
        def flush(self):
            self.stream.flush()

    sys.stdout = LogFilter(sys.stdout)
    sys.stderr = LogFilter(sys.stderr)

# --- CORE LOGIC & HELPERS ---

def b64(s: str) -> str:
    """Encodes a string into Base64 for safe embedding in HTML."""
    return base64.b64encode(s.encode('utf-8')).decode('ascii')

def load_text(path: str | None) -> str:
    """Safely loads text from a file path."""
    if not path:
        return ''
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception as e:
        print(f"[error] Failed to read file: {path}\n{e}", file=sys.stderr)
        return f"<unable to read {html.escape(str(path))}>"

def get_asset_path(filename: str) -> str:
    """Resolves path to the assets directory relative to this script."""
    # src/app.py -> project_root/assets/filename
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, 'assets', filename)

def load_and_combine_ui() -> str:
    """Reads UI files from assets/ and combines them."""
    try:
        with open(get_asset_path('index.html'), 'r', encoding='utf-8') as f:
            html_template = f.read()
        with open(get_asset_path('style.css'), 'r', encoding='utf-8') as f:
            css_text = f.read()
        with open(get_asset_path('index.js'), 'r', encoding='utf-8') as f:
            js_text = f.read()
    except FileNotFoundError as e:
        print(f"[fatal] UI file not found: {e}. Ensure assets are in the 'assets/' directory.", file=sys.stderr)
        sys.exit(1)
    return html_template.replace('%CSS%', css_text).replace('%JS%', js_text)

class Api:
    """The API class exposed to the JavaScript frontend."""
    def __init__(self):
        self.window: webview.Window | None = None
        self._active_path: str | None = None
        self._active_is_dirty: bool = False
        self._boot: dict | None = None

    def get_boot_data(self) -> dict:
        return self._boot or {}

    def create_alert(self, title: str, message: str):
        if self.window:
            self.window.create_alert(title, message)

    def confirm_dialog(self, title: str, message:str) -> bool:
        if self.window:
            return self.window.create_confirmation_dialog(title, message)
        return False

    def set_active_tab(self, path: str | None, is_dirty: bool):
        self._active_path = path
        self._active_is_dirty = is_dirty
        self._update_title()

    def open_dialog(self) -> dict:
        assert self.window is not None
        result = self.window.create_file_dialog(FileDialog.OPEN, allow_multiple=False, file_types=("All files (*.*)",))
        if not result or not isinstance(result, (list, tuple)) or not result[0]:
            return {'cancelled': True}
        path = result[0]
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            return {'cancelled': False, 'path': path, 'text': text}
        except Exception as e:
            self.window.create_alert('File Open Error', f'Failed to read file:\n{path}\n\n{e}')
            return {'cancelled': True}

    def save_dialog(self, content: str, path: str | None) -> dict:
        return self._save_logic(content, path, force_dialog=False)

    def save_as_dialog(self, content: str, path: str | None) -> dict:
        return self._save_logic(content, path, force_dialog=True)

    def _save_logic(self, content: str, path: str | None, force_dialog: bool) -> dict:
        assert self.window is not None
        if not path or force_dialog:
            result = self.window.create_file_dialog(
                FileDialog.SAVE,
                directory=os.path.dirname(path) if path else '',
                save_filename=os.path.basename(path) if path else 'untitled.txt',
                file_types=("All files (*.*)",)
            )
            if not result:
                return {'saved': False}
            path = result[0] if isinstance(result, (tuple, list)) and len(result) > 0 else result

        if not path:
             return {'saved': False}

        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.set_active_tab(path, is_dirty=False)
            return {'saved': True, 'path': path}
        except Exception as e:
            self.window.create_alert('Save Error', f'Failed to save to {path}\n{e}')
            return {'saved': False, 'error': str(e)}

    def quit(self):
        if self.window:
            self.window.destroy()

    def _update_title(self):
        if not self.window:
            return
        base = os.path.basename(self._active_path) if self._active_path else 'Untitled'
        # Hide NamedTemporaryFile suffixes
        if base.lower().startswith("untitled-") and base.lower().endswith(".txt"):
            base = "Untitled"
        dirty_indicator = '●' if self._active_is_dirty else ''
        self.window.set_title(f"{base}{dirty_indicator} - Monaco Viewer")

# --- GUI MODE (Default / Showcase) ---

def run_gui(file=None, sline=None, eline=None, scol=None, ecol=None,
            replace_text=None, autosave=False, theme='vs-dark',
            lang=None, read_only=False):
    """Launches the PyWebView GUI."""
    
    # Path handling
    path = os.path.abspath(file) if file else None
    text = load_text(path)
    base = os.path.basename(path) if path else ""
    is_untitled = (not base) or (base.lower().startswith("untitled-") and base.lower().endswith(".txt"))
    display_name = "Untitled" if is_untitled else base

    # Prepare Boot Data
    boot = {
        'text': text, 'path': path, 'sline': sline, 'eline': eline, 'scol': scol, 'ecol': ecol,
        'replaceText': replace_text, 'autosave': autosave, 'theme': theme, 'lang': lang,
        'readOnly': read_only, 'displayName': display_name, 'isUntitled': is_untitled,
    }
    
    api = Api()
    api._boot = boot
    
    # Inject Boot Data into HTML
    try:
        final_html = load_and_combine_ui().replace('%BOOT%', b64(json.dumps(boot)))
    except Exception as e:
        print(f"Error preparing UI: {e}")
        return

    # Native Menus
    menu_items = [
        Menu('File', [
            MenuAction('New', lambda: api.window.evaluate_js('window.__doNew()')),
            MenuAction('Open', lambda: api.window.evaluate_js('window.__doOpen()')),
            MenuAction('Save', lambda: api.window.evaluate_js('window.__doSave()')),
            MenuAction('Save As...', lambda: api.window.evaluate_js('window.__doSaveAs()')),
            MenuSeparator(),
            MenuAction('Quit', api.quit)
        ]),
        Menu('Edit', [
            MenuAction('Undo', lambda: api.window.evaluate_js('window.__doUndo()')),
            MenuAction('Redo', lambda: api.window.evaluate_js('window.__doRedo()')),
            MenuSeparator(),
            MenuAction('Cut', lambda: api.window.evaluate_js('window.__doCut()')),
            MenuAction('Copy', lambda: api.window.evaluate_js('window.__doCopy()')),
            MenuAction('Paste', lambda: api.window.evaluate_js('window.__doPaste()')),
            MenuSeparator(),
            MenuAction('Find / Replace', lambda: api.window.evaluate_js('window.__showFindReplace()')),
            MenuSeparator(),
            MenuAction('Agent Surgical Replace...', lambda: api.window.evaluate_js('window.__showSurgicalReplace()'))
        ])
    ]

    win = webview.create_window(
        title="Monaco Viewer", html=final_html, width=1100, height=750,
        js_api=api, confirm_close=True, menu=menu_items
    )
    api.window = win

    def set_icon():
        icon_path = get_asset_path('monaco-viewer-icon.png')
        if webview.windows and hasattr(webview.windows[0], 'gui_window'):
            native_win = webview.windows[0].gui_window
            if native_win and os.path.exists(icon_path):
                try:
                    native_win.setWindowIcon(QIcon(icon_path))
                except Exception:
                    pass

    # Suppress output during launch
    with open(os.devnull, 'w') as f, contextlib.redirect_stderr(f):
        webview.start(set_icon, gui='qt', debug=False)

# --- CLI MODE (Utility) ---

def run_cli():
    """Handles command-line arguments for headless tasks or configured GUI launch."""
    ap = argparse.ArgumentParser(description='Monaco Viewer - Code Editor & Utility')
    
    # GUI Arguments
    ap.add_argument('--file', nargs='?', default=None, help='Path to file to open.')
    ap.add_argument('--untitled', action='store_true', help='Start a new Untitled buffer.')
    ap.add_argument('--sline', type=int, help='Start line.')
    ap.add_argument('--eline', type=int, help='End line.')
    ap.add_argument('--scol', type=int, help='Start column.')
    ap.add_argument('--ecol', type=int, help='End column.')
    ap.add_argument('--replace-text', type=str, help='Text to insert.')
    ap.add_argument('--autosave', action='store_true', help='Autosave after replace.')
    ap.add_argument('--theme', type=str, default='vs-dark', help='vs, vs-dark.')
    ap.add_argument('--lang', type=str, help='Force language.')
    ap.add_argument('--read-only', action='store_true', help='Read-only mode.')

    # Headless Arguments
    ap.add_argument('--regex-find', type=str, help='[HEADLESS] Regex pattern.')
    ap.add_argument('--regex-replace', type=str, help='[HEADLESS] Replacement string.')

    args = ap.parse_args()

    # --- Headless Logic ---
    if args.regex_find and args.regex_replace:
        if not args.file:
            print("[error] --file is required for headless regex mode.", file=sys.stderr)
            sys.exit(2)
        if not os.path.exists(args.file):        
            print(f"[error] File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            new_content, count = re.subn(args.regex_find, args.regex_replace, content)

            if content != new_content:
                with open(args.file, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Successfully made {count} replacement(s) in {args.file}")
            else:
                print("No matches found. File was not changed.")
        except Exception as e:
            print(f"[error] Headless error: {e}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)

    # --- Configured GUI Launch ---
    # Handle temp file for "Untitled" logic
    if args.untitled or args.file is None:
        from tempfile import NamedTemporaryFile
        tmp = NamedTemporaryFile(mode="w+", suffix=".txt", prefix="Untitled-", delete=False)
        tmp.close()
        args.file = tmp.name

    # Infer language
    if not args.lang and args.file:
        ext = os.path.splitext(args.file)[1].lower()
        args.lang = {
            '.py':'python','.js':'javascript','.ts':'typescript','.json':'json',
            '.md':'markdown','.html':'html','.css':'css','.txt':'plaintext',
            '.c':'c','.cpp':'cpp','.h':'c','.hpp':'cpp','.sh':'shell','.ini':'ini',
        }.get(ext, 'plaintext')

    run_gui(
        file=args.file, sline=args.sline, eline=args.eline, scol=args.scol, ecol=args.ecol,
        replace_text=args.replace_text, autosave=args.autosave, theme=args.theme,
        lang=args.lang, read_only=args.read_only
    )

def main():
    apply_log_filter()
    if len(sys.argv) > 1:
        run_cli()
    else:
        # Default Showcase / Empty Launch
        from tempfile import NamedTemporaryFile
        tmp = NamedTemporaryFile(mode="w+", suffix=".txt", prefix="Untitled-", delete=False)
        tmp.close()
        run_gui(file=tmp.name, theme='vs-dark', lang='plaintext')

if __name__ == "__main__":
    main()