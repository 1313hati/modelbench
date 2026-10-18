Review the Python code below. Report every genuine correctness or resource-safety
defect. Ignore style, naming, type hints, missing docstrings and micro-optimisations.

Return a JSON array (and nothing else) where each finding is:

```json
{"file": "accounts.py", "line": 12, "severity": "high", "issue": "one sentence"}
```

`line` must be the line where the defect is most directly visible. Do not report
the same defect twice. If code is correct, do not invent a finding.

### accounts.py
```python
     1| class Account:
     2|     def __init__(self, owner, balance=0):
     3|         self.owner = owner
     4|         self.balance = balance
     5|
     6|     def deposit(self, amount):
     7|         if amount <= 0:
     8|             raise ValueError("amount")
     9|         self.balance += amount
    10|
    11|     def withdraw(self, amount):
    12|         if amount <= 0:
    13|             raise ValueError("amount")
    14|         if amount > self.balance:
    15|             raise ValueError("insufficient funds")
    16|         self.balance -= amount
    17|
    18|     def transfer(self, target, amount):
    19|         self.withdraw(amount)
    20|         target.deposit(amount)
    21|
    22|     def history(self, entries=[]):
    23|         entries.append(self.balance)
    24|         return entries
```

### pricing.py
```python
     1| def apply_discount(price, percent):
     2|     if percent < 0 or percent > 100:
     3|         raise ValueError("percent")
     4|     return price - price * percent / 100
     5|
     6| def tax_for(price, region):
     7|     if region == "EU":
     8|         return price * 0.2
     9|     if region is "US":
    10|         return price * 0.07
    11|     return 0
    12|
    13| def total(price, percent, region):
    14|     discounted = apply_discount(price, percent)
    15|     return discounted + tax_for(price, region)
```

### files.py
```python
     1| import os
     2|
     3| def read_lines(path):
     4|     f = open(path)
     5|     data = f.read()
     6|     return data.splitlines()
     7|
     8| def write_lines(path, lines):
     9|     with open(path, "w") as f:
    10|         for line in lines:
    11|             f.write(line)
    12|             f.write("\n")
    13|
    14| def copy_file(src, dst):
    15|     data = read_lines(src)
    16|     write_lines(dst, data)
    17|
    18| def find_files(root, ext):
    19|     out = []
    20|     for base, _dirs, files in os.walk(root):
    21|         for name in files:
    22|             if name.endswith("." + ext):
    23|                 out.append(os.path.join(base, name))
    24|     return out
```

### cache.py
```python
     1| class Cache:
     2|     def __init__(self, size=100):
     3|         self.size = size
     4|         self.data = {}
     5|
     6|     def get(self, key):
     7|         return self.data.get(key)
     8|
     9|     def put(self, key, value):
    10|         if len(self.data) >= self.size:
    11|             self.data.clear()
    12|         self.data[key] = value
```

### retry.py
```python
     1| def retry(fn, attempts=3):
     2|     last = None
     3|     for _ in range(attempts):
     4|         try:
     5|             return fn()
     6|         except Exception:
     7|             last = None
     8|     raise last
```

### lock.py
```python
     1| import threading
     2|
     3| class Counter:
     4|     def __init__(self):
     5|         self.value = 0
     6|         self.lock = threading.Lock()
     7|
     8|     def increment(self):
     9|         current = self.value
    10|         self.value = current + 1
```

Return only the JSON array.
