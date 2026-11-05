import Foundation

class OrderModel {
    var id: String
    var items: [String]
    init(id: String, items: [String]) { self.id = id; self.items = items }
}

final class OrderService {
    func fetch(id: String, completion: @escaping (Result<OrderModel, Error>) -> Void) {
        completion(.success(OrderModel(id: id, items: [])))
    }
}
