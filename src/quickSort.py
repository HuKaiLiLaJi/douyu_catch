def quick_sort(numbers):
    """Return a new sorted list using quick sort."""
    if len(numbers) <= 1:
        return numbers[:]

    pivot = numbers[-1]
    left = [num for num in numbers[:-1] if num <= pivot]
    right = [num for num in numbers[:-1] if num > pivot]

    return quick_sort(left) + [pivot] + quick_sort(right)


if __name__ == "__main__":
    sample = [5, 3, 8, 4, 2, 7, 1, 10]
    print(quick_sort(sample))
