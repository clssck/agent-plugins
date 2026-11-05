workspace {
  model {
    customer = person "Customer"
    orders = softwareSystem "Orders" {
      web = container "Web app"
      api = container "Orders API"
      db = container "Orders DB"
    }
    customer -> web "Uses"
    web -> api "Calls"
    api -> db "Reads and writes"
  }
}
