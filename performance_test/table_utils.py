def write_text_table(path, header, rows, col_widths=None):
    if col_widths is None:
        col_widths = [
            max(len(str(item))
                for item in [header[idx], *[row[idx] for row in rows]]) + 2
            for idx in range(len(header))
        ]

    with open(path, "w") as f:
        header_line = "".join(
            f"{str(header[idx]):<{col_widths[idx]}}" for idx in range(len(header))
        )
        f.write(f"{header_line}\n")
        f.write("-" * len(header_line))
        f.write("\n")

        for row in rows:
            line = "".join(
                f"{str(row[idx]):<{col_widths[idx]}}" for idx in range(len(row))
            )
            f.write(f"{line}\n")
