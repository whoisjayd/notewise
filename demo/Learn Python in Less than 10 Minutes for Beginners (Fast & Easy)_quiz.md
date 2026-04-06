## Python Quick Start Quiz

## Python Fundamentals & Variables

**Q1.** According to the video, which of the following is a correct naming convention for a Python variable with multiple words?

A) `item-name`
B) `ItemName`
C) `item_name`
D) `item name`

**Answer: C)**
**Explanation:** The video states that a naming convention in Python for multiple-word variables is to add an underscore (e.g., `item_name`).

**Q2.** Which statement accurately describes Python's case sensitivity for variables?

A) `item` and `Item` refer to the same variable.
B) Python ignores case for variable names.
C) `item` and `Item` refer to different variables.
D) Variable names must always start with a lowercase letter.

**Answer: C)**
**Explanation:** The video explicitly states that "item with a small i and item with a big i are going to mean absolutely different things," indicating Python is case-sensitive.

## Data Types & Operations

**Q3.** In Python, what data type is used to represent a simple true or false value?

A) Integer
B) String
C) Boolean
D) List

**Answer: C)**
**Explanation:** Booleans are described as a data type that is "just a simple true or false."

**Q4.** A programmer wants to combine the text "Hello" with a variable `user_name` which holds a string value. Which operation would correctly achieve this in Python?

A) `print("Hello" - user_name)`
B) `print("Hello" * user_name)`
C) `print("Hello" + user_name)`
D) `print("Hello" / user_name)`

**Answer: C)**
**Explanation:** The video demonstrates string concatenation (combining text) using the `+` operator.

**Q5.** If you have an integer variable `number = 22` and you want to combine it with a string like "The answer is ", what must you do before concatenating them?

A) Convert the string to an integer.
B) Convert the integer to a string.
C) Use a different operator like `*`.
D) It's not possible to combine different data types.

**Answer: B)**
**Explanation:** The video explains that to combine an integer with a string, the integer must first be converted to a string using `str()` to avoid an exception.

**Q6.** Which Python operator is used to calculate the exponential power of a number (e.g., 2 to the power of 3)?

A) `**`
B) `^`
C) `//`
D) `%`

**Answer: A)**
**Explanation:** The video states that to perform exponential power, you "just add two asterisks" (`**`).

## Control Flow (Logic & Loops)

**Q7.** Consider the following Python code:
```python
age = 15
if age > 21:
    print("You are old")
elif age == 18:
    print("You are getting old")
else:
    print("You are still young")
```
What will be the output when this code runs?

A) You are old
B) You are getting old
C) You are still young
D) (No output, causes an error)

**Answer: C)**
**Explanation:** Since `age` (15) is neither greater than 21 nor equal to 18, the `else` block will be executed, printing "You are still young".

**Q8.** What is the starting index for `i` in a `for i in range(3)` loop in Python, according to the video?

A) 1
B) 3
C) 0
D) Undefined

**Answer: C)**
**Explanation:** The video specifies that "in programming the index always starts at 0" for loops using `range()`.

**Q9.** To exit an infinite `while True` loop based on user input, what keyword is demonstrated in the video?

A) `exit`
B) `stop`
C) `break`
D) `return`

**Answer: C)**
**Explanation:** The video shows using the `break` keyword to "cancel the loop" and terminate its execution when a specific condition is met.

## Functions & Error Handling

**Q10.** What is the primary benefit of using functions in programming, as highlighted in the video?

A) To make code run faster.
B) To reduce the number of variables.
C) To reuse code in many different instances.
D) To make code harder to understand for others.

**Answer: C)**
**Explanation:** The video states that functions are used "to reuse your code in many different instances" to maximize code reusability.

**Q11.** If you define a function but don't have its logic ready yet, what keyword can you use inside the function body to prevent an error when running the program?

A) `skip`
B) `void`
C) `pass`
D) `none`

**Answer: C)**
**Explanation:** The `pass` keyword allows you to create an empty function body without causing an error, serving as a placeholder for future implementation.

**Q12.** What is the main purpose of a `try` and `except` block in Python?

A) To define a new function.
B) To create a conditional loop.
C) To handle potential errors gracefully without crashing the program.
D) To convert data types automatically.

**Answer: C)**
**Explanation:** The `try` and `except` block is used to attempt execution of code that might cause an error, and if an exception occurs, the `except` block handles it to prevent the program from crashing.

**Q13.** Which scenario would most likely cause an `except` block to execute in a `try-except` structure like the one demonstrated for user input?

A) The user enters a valid number.
B) The user enters an empty string.
C) The user enters text that cannot be converted to an integer.
D) The user enters a number greater than 100.

**Answer: C)**
**Explanation:** As shown in the video, if the user enters non-numeric text (like "mario") when an integer conversion is attempted within the `try` block, it will raise an exception and trigger the `except` block.

## Answer Key
Q1 – C
Q2 – C
Q3 – C
Q4 – C
Q5 – B
Q6 – A
Q7 – C
Q8 – C
Q9 – C
Q10 – C
Q11 – C
Q12 – C
Q13 – C