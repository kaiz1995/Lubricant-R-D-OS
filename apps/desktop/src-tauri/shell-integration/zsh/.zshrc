# Open Science terminal integration (see terminal_env.rs): run the user's
# .zshrc, then restore what they exported by hand before the app last closed,
# and keep recording it at every prompt.
if [[ -n ${__osd_user_zdotdir+x} ]]; then
  ZDOTDIR=$__osd_user_zdotdir
else
  unset ZDOTDIR
fi
# /etc/zshrc ran while ZDOTDIR still pointed at this folder: point what it
# derived from it back at the user's own.
[[ $HISTFILE == $__osd_wrapper/.zsh_history ]] && HISTFILE=${ZDOTDIR:-$HOME}/.zsh_history
[[ -r ${ZDOTDIR:-$HOME}/.zkbd/${TERM}-${VENDOR} ]] && builtin source "${ZDOTDIR:-$HOME}/.zkbd/${TERM}-${VENDOR}"
unset __osd_wrapper __osd_user_zdotdir
[[ -f ${ZDOTDIR:-$HOME}/.zshrc ]] && builtin source "${ZDOTDIR:-$HOME}/.zshrc"

# The environment as the startup files leave it. Only what differs from this
# is recorded: the startup files run again on every launch anyway.
typeset -gA __osd_env_base
() {
  local k
  for k in ${(k)parameters[(R)*export*]}; do __osd_env_base[$k]=${(P)k}; done
}
[[ -n $OSD_TERM_ENV_FILE && -r $OSD_TERM_ENV_FILE ]] && builtin source "$OSD_TERM_ENV_FILE"
typeset -g __osd_env_last=

__osd_env_save() {
  local status_=$? k out=
  [[ -n $OSD_TERM_ENV_FILE ]] || return $status_
  for k in ${(ok)parameters[(R)*export*]}; do
    case $k in PWD|OLDPWD|SHLVL|_|ZDOTDIR|OSD_TERM_ENV_FILE) continue ;; esac
    if (( ! ${+__osd_env_base[$k]} )) || [[ ${__osd_env_base[$k]} != "${(P)k}" ]]; then
      out+="export $k=${(q)${(P)k}}"$'\n'
    fi
  done
  for k in ${(ok)__osd_env_base}; do
    [[ ${parameters[$k]} == *export* ]] || out+="unset $k"$'\n'
  done
  if [[ $out != "$__osd_env_last" ]]; then
    if [[ -n $out ]]; then
      print -rn -- "$out" >| "$OSD_TERM_ENV_FILE.tmp" 2>/dev/null &&
        command mv -f "$OSD_TERM_ENV_FILE.tmp" "$OSD_TERM_ENV_FILE" 2>/dev/null
    else
      command rm -f "$OSD_TERM_ENV_FILE" 2>/dev/null
    fi
    __osd_env_last=$out
  fi
  return $status_
}
typeset -ga precmd_functions
precmd_functions+=(__osd_env_save)
