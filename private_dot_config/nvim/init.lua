-- bootstrap lazy.nvim, LazyVim and your plugins
require("config.lazy")

vim.api.nvim_create_user_command("Dashboard", function()
  require("snacks").dashboard.open()
end, { desc = "Open Snacks Dashboard" })

vim.keymap.set("n", "<leader>D", ":Dashboard<CR>", { noremap = true, silent = true })
