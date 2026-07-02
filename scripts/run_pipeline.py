import os
import sys

if __name__ == "__main__":
    # Ensure working directory is the project root
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    # Run generate synthetic data
    print("Running synthetic data generation...")
    import scripts.generate_synthatic_data as gen
    w, a, c = gen.generate_dummy_data()
    gen.insert_data(w, a, c)

    # Import and execute main pipeline
    print("Running main scoring pipeline...")
    from src.main import main
    # We simulate calling main() with `--mode SCORE`
    # Let's override sys.argv
    sys.argv = ["main.py", "--mode", "SCORE"]
    main()
