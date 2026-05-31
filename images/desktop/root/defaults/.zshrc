# Oh My Zsh configuration
export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME="agnoster"

plugins=(
    git
    docker
    python
    pip
    uv
    fzf
    command-not-found
    colored-man-pages
    extract
    z
)

source $ZSH/oh-my-zsh.sh 2>/dev/null || true

# Zsh plugins (system-installed)
source /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh 2>/dev/null
source /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh 2>/dev/null

# Aliases
alias ls='eza --icons --group-directories-first'
alias ll='eza -la --icons --group-directories-first'
alias lt='eza --tree --icons --level=2'
alias cat='batcat --style=plain'
alias fd='fdfind'
alias top='htop'
alias py='python3'

# UV completions
eval "$(uv generate-shell-completion zsh 2>/dev/null)"

# FZF integration
source /usr/share/doc/fzf/examples/key-bindings.zsh 2>/dev/null
source /usr/share/doc/fzf/examples/completion.zsh 2>/dev/null

# Path
export PATH="$HOME/.local/bin:$PATH"
