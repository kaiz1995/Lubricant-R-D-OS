# Open Science terminal integration (see terminal_env.rs). zsh reads its
# startup files from $ZDOTDIR, which points here so that .zshrc below runs
# after the user's own. Everything else is the user's: their ZDOTDIR is put
# back while their files run.
__osd_wrapper=$ZDOTDIR
if [[ -n ${OSD_USER_ZDOTDIR+x} ]]; then
  export ZDOTDIR=$OSD_USER_ZDOTDIR
else
  unset ZDOTDIR
fi
unset OSD_USER_ZDOTDIR
[[ -f ${ZDOTDIR:-$HOME}/.zshenv ]] && builtin source "${ZDOTDIR:-$HOME}/.zshenv"
# The user's .zshenv may itself move ZDOTDIR; remember what it ended as.
[[ -n ${ZDOTDIR+x} ]] && __osd_user_zdotdir=$ZDOTDIR
ZDOTDIR=$__osd_wrapper
