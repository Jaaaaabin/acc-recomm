from src.utils.env_utils import show_system_info, print_tree
from src.utils.time_utils import measure_runtime
# from utils.cli_utils import print_info, print_success, progress_iter

@measure_runtime
def main():
    print("=" * 70)
    print("ACC-RECOMM – General Environment Summary")
    print("=" * 70)

    show_system_info()
    print_tree(root=".", max_depth=3)

    print("\n✅ Environment summary complete.\n")

if __name__ == "__main__":

    main()
