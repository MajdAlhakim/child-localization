package qa.qu.trakn.aptool.data.api

import okhttp3.ResponseBody
import qa.qu.trakn.aptool.data.models.AccessPoint
import qa.qu.trakn.aptool.data.models.GenericOkResponse
import qa.qu.trakn.aptool.data.models.GetApsResponse
import qa.qu.trakn.aptool.data.models.HealthResponse
import qa.qu.trakn.aptool.data.models.PostApRequest
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST

interface ApiService {

    @GET("/health")
    suspend fun health(): HealthResponse

    @GET("/api/v1/venue/floor-plan")
    suspend fun getFloorPlan(): Response<ResponseBody>

    @GET("/api/v1/venue/aps")
    suspend fun getAps(
        @Header("X-API-Key") apiKey: String,
    ): GetApsResponse

    @POST("/api/v1/venue/ap")
    suspend fun postAp(
        @Header("X-API-Key") apiKey: String,
        @Body body: PostApRequest,
    ): GenericOkResponse

    @DELETE("/api/v1/venue/aps")
    suspend fun deleteAllAps(
        @Header("X-API-Key") apiKey: String,
    ): Response<GenericOkResponse>
}
