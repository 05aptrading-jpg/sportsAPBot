import re
import subprocess
import os

os.chdir(r"D:\Apuestas\mlb_bot")
os.environ["FILTER_BRANCH_SQUELCH_WARNING"] = "1"

# Use git filter-branch with a simple sed-like replacement
# Write a shell script for the filter
filter_script = r"""
import re, sys
content = sys.stdin.read()
new_content = re.sub(r'ghp_[A-Za-z0-9]+', 'REMOVED_TOKEN_VALUE', content)
sys.stdout.write(new_content)
"""

with open("_filter.py", "w") as f:
    f.write(filter_script)

# Use python-based tree filter
cmd = [
    "git", "filter-branch", "--force", "--tree-filter",
    "python _filter.py < config.py > config.py.tmp && mv config.py.tmp config.py",
    "052e7b88~1..HEAD"
]

result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
print("STDOUT:", result.stdout[-500:] if result.stdout else "")
print("STDERR:", result.stderr[-500:] if result.stderr else "")
print("RC:", result.returncode)
