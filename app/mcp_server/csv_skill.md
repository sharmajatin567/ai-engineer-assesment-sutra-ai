# CSV Analysis Skill — Branch Revenue & Orders

The dataset `Branch_Revenue_Orders.csv` has one row per branch, quarter and product category.

## How to answer with the tools
- Call `csv_schema()` first if you are unsure of the column names. Record the exact column names 
- Use `operate_on_csv()` performing operations on the csv: 
  - For arg "code": Generate python code to fetch/read any particular information from an already initialized dataframe of the csv named "df".
  - You can iterate on this tool multiple times to perform df operations on the df and calculate the output.
  - For every iteration of the tool, you will always get a fresh copy of the csv in the variable "df".
  - Attempt to get your desired output in not more than **2 Iterations**. 
  - *Important* : Always store the output in the variable "result". This will be the variable to be used to read the output of the code you generated. 
  - **CRITICAL** : Do not attempt to read the full dataframe, or perform manipulations on the csv file directly. Always use the available "df" variable to read aggregated outputs, grouped data, etc. 
## Examples
- "Total Sales for each category: " -> code = """
    result = data.groupby("category")["sales"].sum()
    print(result)
    """
