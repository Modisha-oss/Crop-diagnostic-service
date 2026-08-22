# ==========================================
# MODISHA'S AGRICULTURAL AI ASSISTANT
# PROJECT 1 - VERSION 1
# ==========================================

print("==========================================")
print("       MODISHA'S AGRICULTURAL' AI ASSISTANT")
print("==========================================")
print()

# ------------------------------------------
# FARMER / SITE INFORMATION
# ------------------------------------------

site_location = input("Site Location: ")

region = input("Region: ")

vegetable = input("Vegetable Type: ")

weekly_observation = input(
    "What did you observe this week? "
)

farmer_email = input(
    "Farmer Email: "
)

# ------------------------------------------
# DISPLAY THE INFORMATION
# ------------------------------------------

print()
print("==========================================")
print("          WEEKLY FARM REPORT")
print("==========================================")

print("Site:", site_location)
print("Region:", region)
print("Vegetable:", vegetable)
print("Observation:", weekly_observation)
print("Email:", farmer_email)

print()
print("Report successfully captured.")
