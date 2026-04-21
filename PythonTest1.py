names = ["Alice", "Bob", "Andrew", "Charlie", "Amy", "David"]
debts = [5.94,    -5.49, -20.00,    15.75,     -8.50, 12.30]

# Check if list of debts is as long a list of names
if len(names) != len(debts):
    print("Error: The number of names and debts do not match.")

# Check if debts sum to zero
total_debt = sum(debts)
if total_debt != 0:
    print("Error: The total debt does not sum to zero.")
    print(f"Total debt: {total_debt}")
else:
    print("All checks passed. The debts are valid.")

# Solve for the amount each person owes to each other

# Sort by debts in descending order (largest to smallest)
sorted_pairs = sorted(zip(names, debts), key=lambda x: x[1], reverse=True)
names, debts = zip(*sorted_pairs)
names = list(names)
debts = list(debts)

# Create a list to store the transactions
transactions = []

# Loop through the sorted lists and create transactions
for i in range(len(names)):
    for j in range(i + 1, len(names)):
        if debts[i] > 0 and debts[j] < 0:
            amount = min(debts[i], -debts[j])
            transactions.append((names[i], names[j], amount))
            debts[i] -= amount
            debts[j] += amount

# Print the transactions
for transaction in transactions:
    print(f"{transaction[0]} owes {transaction[1]}: ${transaction[2]:.2f}")