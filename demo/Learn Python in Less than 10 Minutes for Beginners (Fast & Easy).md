# Python Fundamentals: A Quick Start Guide

This guide provides a comprehensive overview of fundamental Python concepts, using Python 3.8 and PyCharm as the development environment. Python and PyCharm are free and open-source tools, easily found via a quick search.

## 1. Variables and Value Assignment

In Python, a variable is a named storage location for data. Assigning a value to a variable is straightforward.

### 1.1 Creating Variables and Assigning Values

To create a variable, you choose a name and then use the assignment operator (`=`) to give it a value.

*   **Example**:
    ```python
    item = "banana" # Assigns the string "banana" to the variable 'item'
    ```

### 1.2 Strings

A string is a data type used to represent text. In Python, strings are enclosed in quotation marks (single or double).

*   **Example**:
    ```python
    item = "banana" # "banana" is a string
    item_name = "orange" # "orange" is another string
    ```

### 1.3 Case Sensitivity

Python is a case-sensitive language. This means that variables with the same name but different capitalization are treated as entirely distinct variables.

*   **Example**:
    ```python
    item = "banana"
    Item = "apple"
    # 'item' and 'Item' refer to different storage locations and values.
    # Printing both will show:
    # banana
    # apple
    ```

### 1.4 Naming Conventions

For variables composed of multiple words, the standard Python naming convention is to separate words with underscores (`_`). This is known as `snake_case`.

*   **Example**:
    ```python
    item_name = "orange" # Recommended naming convention for multi-word variables
    ```

### 1.5 Combining Text (String Concatenation)

You can combine strings using the `+` operator.

*   **Example**:
    ```python
    item_name = "orange"
    print("hello" + item_name) # Output: helloorange
    ```
    Note: If you want a space between "hello" and "orange", you need to include it in one of the strings: `print("hello " + item_name)` or `print("hello" + " " + item_name)`.

## 2. Data Types

Python automatically infers the data type of a variable based on the value assigned to it. Here are some fundamental data types:

### 2.1 Integers

Integers are whole numbers (positive, negative, or zero) without a decimal component. They are often displayed in blue in code editors like PyCharm.

*   **Example**:
    ```python
    year = 2021 # 'year' is an integer
    age = 28 # 'age' is an integer
    ```

### 2.2 Strings

As discussed, strings represent text and are enclosed in quotation marks.

*   **Example**:
    ```python
    text_value = "This is some text" # 'text_value' is a string
    string_number = "22" # Even though it looks like a number, the quotes make it a string
    ```

### 2.3 Booleans

Booleans represent truth values: `True` or `False`. They are essential for logic and conditional statements.

*   **Example**:
    ```python
    is_happy = True   # 'is_happy' is a boolean
    is_valid = False  # 'is_valid' is a boolean
    ```

### 2.4 Lists

A list is an ordered, mutable (changeable) collection of items. Lists are defined using square brackets `[]`, and items are separated by commas. Lists can contain items of different data types (e.g., numbers, strings, booleans).

*   **Example**:
    ```python
    my_list = [2021, "text", False] # A list containing an integer, a string, and a boolean
    name_list = ["Mario", "Luigi", "Peach"] # A list of strings
    ```

## 3. Type Conversion (Casting)

Python is a strongly typed language, meaning you cannot directly perform operations (like concatenation or arithmetic) on variables of incompatible types without explicit conversion.

### 3.1 The Need for Type Conversion

When combining different data types, such as a string and an integer, Python will raise an error if you try to do so directly. You must convert them to a compatible type first.

*   **Problem Example**:
    ```python
    name = "Mario"
    number = 22 # This is an integer
    # print(name + number) # This would result in a TypeError
    ```
    The error message would indicate that you can only concatenate `str` (string) to `str`, not `int` (integer).

### 3.2 Converting to String (`str()`)

To combine an integer with a string, you can convert the integer to a string using the `str()` function.

*   **Example**:
    ```python
    name = "Mario"
    number = 22
    print(name + str(number)) # Converts 'number' to "22" (string), then concatenates.
                              # Output: Mario22
    ```

### 3.3 Converting to Integer (`int()`)

Similarly, if you have a string that represents a number and you want to perform mathematical operations on it, you must convert it to an integer (or float) using the `int()` function.

*   **Problem Example**:
    ```python
    string_number = "22" # This is a string
    # print(string_number + 10) # This would result in a TypeError, as you can't add a string and an integer.
    ```

*   **Solution Example**:
    ```python
    string_number = "22"
    print(int(string_number) + 10) # Converts "22" to 22 (integer), then adds 10.
                                  # Output: 32
    ```

## 4. Mathematical Operations

Python supports standard arithmetic operations.

### 4.1 Operators

| Operator | Description      | Example       | Result |
| :------- | :--------------- | :------------ | :----- |
| `+`      | Addition         | `a + b`       | `15`   |
| `-`      | Subtraction      | `a - b`       | `5`    |
| `*`      | Multiplication   | `a * b`       | `50`   |
| `/`      | Division         | `a / b`       | `2.0`  |
| `**`     | Exponential Power| `a ** b`      | `100000` |

*   **Example**:
    ```python
    a = 10
    b = 5

    print(a + b)  # Output: 15
    print(a - b)  # Output: 5
    print(a * b)  # Output: 50
    print(a / b)  # Output: 2.0 (division always returns a float)
    print(a ** b) # Output: 100000 (10 to the power of 5)
    ```

## 5. Conditional Statements (If-Elif-Else)

Conditional statements allow your program to make decisions based on whether certain conditions are true or false. This is a core concept for controlling program flow.

### 5.1 `if` Statement

The `if` statement executes a block of code only if its condition is `True`.

*   **Syntax**:
    ```python
    if condition:
        # code to execute if condition is True
    ```

### 5.2 `elif` Statement (Else If)

The `elif` (else if) statement allows you to check multiple conditions sequentially. If the `if` condition is `False`, Python checks the `elif` condition. You can have multiple `elif` blocks.

*   **Syntax**:
    ```python
    if condition1:
        # code if condition1 is True
    elif condition2:
        # code if condition1 is False, and condition2 is True
    ```

### 5.3 `else` Statement

The `else` statement provides a fallback. If none of the preceding `if` or `elif` conditions are `True`, the code inside the `else` block is executed.

*   **Syntax**:
    ```python
    if condition1:
        # code if condition1 is True
    elif condition2:
        # code if condition1 is False, and condition2 is True
    else:
        # code if all preceding conditions are False
    ```

### 5.4 Comparison and Logical Operators

*   **Comparison Operators**: Used to compare values (`>`, `<`, `>=`, `<=`, `==` for equality, `!=` for inequality).
*   **Logical Operators**: Used to combine conditions (`and`, `or`, `not`).

### 5.5 Examples

*   **Example with `age`**:
    ```python
    age = 28

    if age > 21:
        print("You are old")
    elif age == 18:
        print("You are getting old")
    else:
        print("You are still young")
    # Output: You are old (because 28 > 21 is True)
    ```

*   **Example with `is_happy` (Boolean condition)**:
    ```python
    is_happy = False

    if is_happy: # This is equivalent to 'if is_happy == True:'
        print("You are happy")
    else:
        print("You are not happy")
    # Output: You are not happy (because 'is_happy' is False)

    is_happy = True
    if is_happy:
        print("You are happy")
    else:
        print("You are not happy")
    # Output: You are happy (because 'is_happy' is True)
    ```
    The `if-else` statement is one of the most frequently used logic constructs in programming.

## 6. Loops

Loops allow you to execute a block of code repeatedly.

### 6.1 `for` Loop

A `for` loop is used for iterating over a sequence (like a list, tuple, dictionary, set, or string) or other iterable objects.

#### 6.1.1 `range()` Function

The `range()` function generates a sequence of numbers.
*   `range(n)` generates numbers from 0 up to (but not including) `n`.
*   The index in programming typically starts at 0.

*   **Example 1: Basic `for` loop with `range(3)`**:
    ```python
    for i in range(3): # Loops three times: for i=0, then i=1, then i=2
        print("Hello", i)
    # Output:
    # Hello 0
    # Hello 1
    # Hello 2
    ```

*   **Example 2: Adjusting `range` output to start from 1**:
    To make the output start from 1 instead of 0, you can add 1 to the loop variable `i`.
    ```python
    for i in range(3):
        print("Hello", i + 1) # Adds 1 to 'i' for printing
    # Output:
    # Hello 1
    # Hello 2
    # Hello 3
    ```

*   **Understanding `range` as an object**:
    `range(n)` doesn't immediately create a list of numbers; it creates a `range` object that efficiently produces numbers as needed.
    ```python
    print(range(3)) # Output: range(0, 3)
    ```
    This `range` object represents the sequence of numbers from 0 up to 3 (exclusive).

#### 6.1.2 Iterating Over Lists with `for` Loop

You can directly iterate over the items in a list.

*   **Example**:
    ```python
    name_list = ["Mario", "Luigi", "Peach"]
    for name in name_list: # 'name' will sequentially take on each value from 'name_list'
        print(name)
    # Output:
    # Mario
    # Luigi
    # Peach
    ```

### 6.2 `while` Loop

A `while` loop repeatedly executes a block of code as long as a given condition remains `True`.

#### 6.2.1 Basic `while` Loop Structure

You need to initialize a variable before the loop and typically update it inside the loop to eventually make the condition `False` and terminate the loop.

*   **Example**:
    ```python
    i = 0 # Initialize 'i'
    while i < 5: # Condition: loop as long as 'i' is less than 5
        i += 1 # Increment 'i' by 1 in each iteration (equivalent to i = i + 1)
        print(i) # Print the current value of 'i'
    # Output:
    # 1
    # 2
    # 3
    # 4
    # 5
    ```
    The loop continues until `i` becomes 5, at which point `i < 5` becomes `False`, and the loop terminates.

#### 6.2.2 Infinite Loops

A `while True` loop will run forever unless explicitly stopped, as its condition is always `True`. This is often used when you want a program to continuously run until a specific user action or internal condition is met.

*   **Example**:
    ```python
    # while True:
    #     print("This will print forever!")
    ```

#### 6.2.3 User Input (`input()`)

The `input()` function prompts the user to enter text from the console and returns that text as a string.

*   **Syntax**:
    ```python
    user_input = input("Enter something: ")
    ```

#### 6.2.4 `break` Statement

The `break` statement is used to immediately exit the innermost `for` or `while` loop, regardless of whether the loop's condition has been met.

*   **Example: Infinite loop with `break` for user exit**:
    ```python
    while True: # This loop will run indefinitely
        user_input = input("Enter something (type '0' to exit): ")
        if user_input == "0": # Check if the user entered "0"
            print("We are done here")
            break # Exit the loop immediately
        else:
            print(f"You entered: {user_input}") # f-string for easy string formatting
    # Program execution:
    # Enter something (type '0' to exit): 10
    # You entered: 10
    # Enter something (type '0' to exit): hello
    # You entered: hello
    # Enter something (type '0' to exit): 0
    # We are done here
    # (Program terminates)
    ```

## 7. Functions

Functions are blocks of organized, reusable code that perform a single, related action. They help in breaking down large programs into smaller, manageable, and modular chunks, promoting code reusability and readability.

### 7.1 Defining a Function (`def`)

Functions are defined using the `def` keyword, followed by the function name, parentheses `()`, and a colon `:`. Parameters (inputs) can be specified inside the parentheses.

*   **Syntax**:
    ```python
    def function_name(parameter1, parameter2):
        # Code block (indented)
        # ...
    ```

### 7.2 Function Naming Convention

Similar to variables, function names in Python typically use `snake_case` for multiple words.

### 7.3 Parameters and Arguments

*   **Parameters**: Variables listed inside the parentheses in the function definition (e.g., `name` in `say_hello(name)`). They are placeholders for values that will be passed into the function.
*   **Arguments**: The actual values passed into the function when it is called (e.g., `"Mario"` in `say_hello("Mario")`).

### 7.4 Purpose: Code Reusability

The main advantage of functions is that they allow you to write a piece of code once and then execute it multiple times with different inputs, without rewriting the entire code block.

*   **Example**:
    ```python
    def say_hello(name): # Defines a function named 'say_hello' that takes one parameter 'name'
        print("Hey there", name) # The function's logic

    # Calling the function multiple times with different arguments
    say_hello("Mario") # Output: Hey there Mario
    say_hello("Luigi") # Output: Hey there Luigi
    ```
    Instead of writing `print("Hey there Mario")` and `print("Hey there Luigi")` separately, the `say_hello` function allows reuse of the `print` statement.

### 7.5 The `pass` Keyword

If you need to define a function (or any block of code) but haven't implemented its logic yet, Python requires the block to have at least one statement. Using `pass` acts as a null operation; nothing happens when it's executed, but it satisfies Python's syntax requirements, preventing an `IndentationError`.

*   **Purpose**:
    *   **Placeholder**: Useful for creating function blueprints or outlines of your program structure before filling in the details.
    *   **Prevents Errors**: Allows the program to run without errors for empty functions.

*   **Example**:
    ```python
    def get_internet_connection():
        pass # Placeholder for future logic

    def run_game():
        pass # Another placeholder

    # When these functions are called, nothing happens, but the program runs without errors.
    get_internet_connection()
    run_game()
    # No output, no errors.
    ```
    This is very useful for planning out the architecture of a larger program.

## 8. Error Handling (Try-Except Block)

Error handling allows your program to gracefully manage runtime errors (exceptions) instead of crashing. The `try-except` block is Python's primary mechanism for this.

### 8.1 `try` Block

The `try` block contains the code that you suspect might raise an exception. If an exception occurs within the `try` block, the execution of that block is immediately stopped, and Python looks for an `except` block to handle it.

### 8.2 `except` Block

The `except` block contains the code that will be executed if an exception occurs in the corresponding `try` block. This allows you to define how your program should respond to specific errors.

### 8.3 How it Works

1.  Python attempts to execute the code inside the `try` block.
2.  If *no* exception occurs, the `except` block is skipped, and the program continues after the `try-except` block.
3.  If an exception *does* occur inside the `try` block, the remaining code in the `try` block is skipped. Python then checks if the `except` block is designed to handle that specific type of exception (or any exception, if not specified).
4.  If a matching `except` block is found, its code is executed.
5.  If no matching `except` block is found, the exception is unhandled, and the program will terminate with an error message.

### 8.4 Example: Handling Invalid User Input

This example demonstrates how to handle a `ValueError` that occurs when trying to convert non-numeric user input into an integer.

*   **Scenario**: We want the user to provide a number. If they type text instead, `int()` will raise a `ValueError`.

*   **Code**:
    ```python
    value_to_add = 10 # A fixed value to add to the user's number

    # Prompt the user for input
    user_input_str = input("Please provide a number: ")

    try:
        # Attempt to convert user input to an integer and perform an operation
        user_number = int(user_input_str) # This line might raise a ValueError
        result = value_to_add + user_number
        print("Result:", result)
    except ValueError: # Catch specifically the ValueError
        # If a ValueError occurs, execute this block
        print("That is not a valid number. Please enter a numerical value.")
    ```

*   **Execution Examples**:
    *   **Valid Input**:
        ```
        Please provide a number: 5
        Result: 15
        ```
        (The `try` block executes successfully, `except` is skipped.)

    *   **Invalid Input**:
        ```
        Please provide a number: Mario
        That is not a valid number. Please enter a numerical value.
        ```
        (The `int("Mario")` call in the `try` block raises a `ValueError`, which is caught by the `except ValueError:` block, and the error message is printed instead of crashing the program.)

The `try-except` block is crucial for building robust applications that can handle unexpected user input or other runtime issues gracefully.