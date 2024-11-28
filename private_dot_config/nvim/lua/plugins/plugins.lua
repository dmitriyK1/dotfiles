require("gitsigns").setup({
  current_line_blame = true,
})

return {
  {
    "smjonas/inc-rename.nvim",
    event = "VeryLazy",
  },
}
