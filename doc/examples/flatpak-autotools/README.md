# Buildstream project using autotools and flatpak

This is an example to build an autotools project in a sandbox using a flatpak runtime to get all the needed deps

## Usage

1. Clone the repo
2. cd into it
3. build with buildstream

        bst build amhello.bst

4. run it

        bst shell amhello.bst hello

5. Expected output

        Hello World!
        This is amhello 1.0.

6. Hack on it!

## Credits

- BuildStream: https://buildstream.gitlab.io/buildstream/
- Flatpak: https://flatpak.org/
- Autotools: https://www.gnu.org/software/automake/manual/html_node/Autotools-Introduction.html
